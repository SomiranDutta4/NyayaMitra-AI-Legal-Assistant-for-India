"""NyayaMitra pipeline: one call to handle() per user message.

  user msg ─► safety rules (Python) ─► LLM 1 (language, English translation, intent, domains, validation)
          ─► checklist engine (Python) ◄─ LLM 2 fact extraction        ─► one question at a time
          ─► retrieval (Python, hard cap) ◄─ LLM 2 search queries
          ─► LLM 2 draft (English, cited JSON) ─► LLM 3 audit (deterministic + semantic)
          ─► max 1 bounded correction ─► deliver / prune unverifiable points / abstain
          ─► deterministic rendering ─► translation to the user's language (numbers checked)
"""

import copy
import json
import re
import uuid
from datetime import date
from typing import Callable, Dict, List, Optional, Tuple

from checklists import engine as ck
from checklists.definitions import NOTED_PREFIX, REPEAT_PREFIX, closing_question, get_field, group_question
from config.settings import (MAX_CLARIFICATION_RETRIES, MAX_GROUNDING_RETRIES, MAX_RETRIEVAL_CALLS,
                             MAX_TOTAL_CLARIFICATIONS, ClarificationStatus, GroundingStatus)
from kb.retriever import LegalDocument, get_kb
from llm.client import LLMClient, LLMError, UsageLog
from llm.llm1_classifier import LLM1Intake, TurnAnalysis
from llm.llm2_agent import LLM2Agent
from llm.llm3_verifier import LLM3Auditor, flatten_answer
from orchestrator.render import ABSTAIN_TEXT, ERROR_TEXT, render_answer
from persistence.db import DatabaseManager, SessionState
from rules.legal_rules import compute_case_facts, fmt_inr, limitation_warning, parse_date
from rules.safety import detect_safety_flags, helpline_block, referral_reasons
from verification.checks import run_deterministic_checks, translation_preserves

NEGATIVE = {"no", "nope", "nothing", "none", "na", "nahi", "nahin", "kuch nahi", "bas", "done", "that's all",
            "thats all", "no thanks", "nothing else", "नहीं", "कुछ नहीं", "बस", "no.", "nah"}
DEFAULT_REPLY = {
    "en": "I'm NyayaMitra. I can help with consumer complaints, rent and property disputes, unpaid salary, contracts, police complaints and family matters. Please tell me what happened, who is involved and when.",
    "hi": "मैं न्यायमित्र हूँ। मैं उपभोक्ता शिकायत, किराया/संपत्ति विवाद, बकाया वेतन, अनुबंध, पुलिस शिकायत और पारिवारिक मामलों में मदद कर सकता हूँ। कृपया बताइए क्या हुआ, कौन शामिल है और कब।",
    "hinglish": "Main NyayaMitra hoon. Main consumer complaint, rent/property dispute, salary na milna, contract, police complaint aur family matters mein madad kar sakta hoon. Please batayein kya hua, kaun involved hai aur kab.",
}
# The user explicitly says they don't know / can't remember / won't say (checked on LLM 1's English translation).
EXPLICIT_DECLINE = re.compile(
    r"\b(don'?t|do not|dont|doesn'?t) (know|remember|recall|have)|\bnot sure\b|\bno idea\b|\bcan'?t (say|remember|recall|tell)|"
    r"\bcannot (say|remember|recall|tell)|\b(won'?t|will not|would rather not|prefer not to) (say|tell|share|answer)|"
    r"\bunknown to me\b|\bskip\b|\bforgot\b|\bforget\b|\bunsure\b|\bnot known\b|\bno clue\b|"
    r"\b(pata|maloom|malum|yaad) nahi|\bnahi (pata|maloom|malum)\b|\bnahi bata(unga|ungi|na)\b|"
    r"पता नहीं|मालूम नहीं|याद नहीं|नहीं पता|नहीं बताऊँग", re.I)
RETRY_WORDS = {"retry", "try again", "again", "please retry", "phir se", "dobara", "dobara try karo", "ok", "okay",
               "continue", "go on", "फिर से", "दोबारा"}
CLOSING = {
    "en": "Alright. If anything changes, or you have another question about this or a new problem, just tell me.",
    "hi": "ठीक है। अगर कुछ बदलता है, या इस बारे में या किसी नई समस्या के बारे में आपका कोई और सवाल है, तो बस बताइए।",
    "hinglish": "Theek hai. Agar kuch badle, ya is baare mein ya kisi nayi problem ke baare mein aur sawaal ho, to bas batayein.",
}
TRANSLATION_NOTE = {
    "hi": "_(कानूनी संदर्भ सटीक रखने के लिए यह जवाब अंग्रेज़ी में दिखाया गया है।)_\n\n",
    "hinglish": "_(Legal references exact rakhne ke liye yeh answer English mein dikhaya gaya hai.)_\n\n",
}


def default_client_factory(role: str, usage: UsageLog):
    return LLMClient(role, usage, timeout=150.0 if role == "translate" else 60.0)


class NyayaMitraPipeline:
    def __init__(self, db: Optional[DatabaseManager] = None,
                 client_factory: Callable[[str, UsageLog], object] = default_client_factory,
                 today: Optional[date] = None):
        self.db = db or DatabaseManager()
        self.client_factory = client_factory
        self.kb = get_kb()
        self.today = today

    # ------------------------------------------------------------------ public
    def new_session_id(self) -> str:
        return str(uuid.uuid4())

    def load(self, session_id: str) -> Optional[SessionState]:
        return self.db.load(session_id)

    def handle(self, session_id: str, message: str, language_override: Optional[str] = None,
               progress: Optional[Callable[[str], None]] = None) -> Tuple[SessionState, str]:
        """Thread-safe: the shared pipeline is never mutated; each message gets its own worker
        with its own LLM clients, usage log and progress callback."""
        worker = copy.copy(self)
        return worker._handle(session_id, message, language_override, progress)

    def _handle(self, session_id, message, language_override, progress):
        state = self.db.load(session_id) or SessionState(session_id=session_id)
        state.language_override = language_override if language_override in ("en", "hi", "hinglish") else None
        usage = UsageLog()
        self._progress_cb = progress
        self.llm1 = LLM1Intake(self.client_factory("llm1", usage))
        self.llm2 = LLM2Agent(self.client_factory("llm2", usage), self.client_factory("translate", usage))
        self.llm3 = LLM3Auditor(self.client_factory("llm3", usage))
        state.last_error = None
        try:
            reply = self._turn(state, message.strip())
        except LLMError as e:
            state.last_error = str(e)[:500]
            if state.status == "PROCESSING":
                state.status = "ERROR"
            if not state.transcript or state.transcript[-1]["role"] != "user":
                state.transcript.append({"role": "user", "display": message, "en": message})
            reply = ERROR_TEXT[self._lang(state)]
        state.transcript.append({"role": "assistant", "display": reply, "en": ""})
        state.usage.extend(usage.calls)
        self.db.save(state)
        return state, reply

    # ------------------------------------------------------------------ helpers
    def _progress(self, label: str) -> None:
        cb = getattr(self, "_progress_cb", None)
        if cb:
            try:
                cb(label)
            except Exception:
                pass

    @staticmethod
    def _lang(state: SessionState) -> str:
        return state.language_override or state.language or "en"

    def _context(self, state: SessionState) -> Dict:
        ctx = {"status": state.status, "domains": state.domains, "case_already_answered": state.status in ("COMPLETED", "ABSTAINED")}
        if state.pending_field:
            f = get_field(state.pending_field)
            ctx["pending_question"] = group_question(f.group, "en") if f else state.pending_field
        if state.status == "AWAITING_ADDITIONAL":
            ctx["pending_question"] = closing_question(state.domains, "en")
        if state.transcript:
            last = next((t for t in reversed(state.transcript) if t["role"] == "assistant"), None)
            if last:
                ctx["last_assistant_message"] = last["display"][:400]
        return ctx

    def _with_helplines(self, state: SessionState, text: str, flags: List[str]) -> str:
        hb = helpline_block(flags, self._lang(state))
        if not hb or all(f"**{n}**" in text for n in re.findall(r"\*\*(\d{3,5})\*\*", hb)):
            return text  # final answers already carry the helpline block
        return f"{hb}\n\n{text}"

    def _reset_case(self, state: SessionState) -> None:
        for k, v in dict(mode="case", domains=[], case_statements_en=[], checklist={}, sub_issues={}, key_date=None, amount_inr=None,
                         pending_field=None, pending_retries=0, questions_asked=0, additional_asked=False,
                         retrieval_calls=0, retrieval_log=[], evidence_ids=[], computed={}, audit_reports=[],
                         answer=None, answer_en_md=None, removed_items=[], grounding_retries=0).items():
            setattr(state, k, v)

    # ------------------------------------------------------------------ turn
    def _turn(self, state: SessionState, message: str) -> str:
        flags = detect_safety_flags(message)
        state.safety_flags = sorted(set(state.safety_flags) | set(flags))
        self._progress("Understanding your message…")
        a: TurnAnalysis = self.llm1.analyze(message, self._context(state))
        if not state.language_locked:
            state.language = a.language
        state.transcript.append({"role": "user", "display": message, "en": a.english})
        lang = self._lang(state)

        # ---- no case open yet
        if state.status in ("NEW", "INTAKE"):
            # a question about the law in general / a hypothetical: answer it from the law, no intake questions
            if a.intent == "GENERAL_QUESTION" and a.domains:
                return self._with_helplines(state, self._general(state, a), flags)
            # any concrete situation that maps to a domain opens a case (an emergency that names
            # what is happening, e.g. "my husband beats me", is a case too; helplines are prepended)
            if a.domains and a.intent not in ("GREETING", "CHITCHAT", "OUT_OF_SCOPE"):
                return self._with_helplines(state, self._start_case(state, a), flags)
            if a.intent in ("VAGUE", "EMERGENCY"):
                state.case_statements_en.append(a.english)  # keep context for when the case is described
            state.status = "INTAKE"
            return self._with_helplines(state, a.reply or DEFAULT_REPLY[lang], flags)

        # ---- a different problem while one is open / answered
        if a.intent == "NEW_CASE" and a.domains:
            self._reset_case(state)
            return self._with_helplines(state, self._start_case(state, a), flags)

        if state.status == "CLARIFYING":
            return self._with_helplines(state, self._clarification(state, a), flags)

        if state.status == "AWAITING_ADDITIONAL":
            said_no = message.lower().strip(" .!") in NEGATIVE or a.clarification_status == ClarificationStatus.DECLINED \
                or a.intent in ("CHITCHAT", "GREETING")
            if not said_no:
                self._add_statement(state, a)
                self._extract(state)
                nxt = self._ask_next(state, allow_additional=False)
                if nxt:
                    return self._with_helplines(state, nxt, flags)
            return self._with_helplines(state, self._answer(state), flags)

        # ---- the last answer failed because a model was unavailable: retry it. Only treat the
        # message as new facts if it actually says something ("retry", "ok" add nothing to the case).
        if state.status == "ERROR":
            if message.lower().strip(" .!?") not in RETRY_WORDS and len(message.split()) > 3 \
                    and a.intent not in ("CHITCHAT", "GREETING"):
                self._add_statement(state, a)
                self._extract(state)
            return self._with_helplines(state, self._answer(state), flags)

        # ---- COMPLETED / ABSTAINED
        if message.lower().strip(" .!") in NEGATIVE or a.clarification_status == ClarificationStatus.DECLINED:
            return CLOSING[lang]
        if a.intent in ("CHITCHAT", "GREETING"):
            return self._with_helplines(state, a.reply or CLOSING[lang], flags)
        if state.mode == "general":
            # after a general answer: another general / follow-up question is answered the same way;
            # describing something that actually happened opens a normal case with intake questions
            if a.intent in ("LEGAL_CASE", "NEW_CASE") and a.domains:
                self._reset_case(state)
                return self._with_helplines(state, self._start_case(state, a), flags)
            if a.domains or a.intent in ("GENERAL_QUESTION", "FOLLOW_UP"):
                if not a.domains:
                    a.domains = list(state.domains)
                return self._with_helplines(state, self._general(state, a), flags)
        new_domains = [d for d in a.domains if d not in state.domains]
        self._add_statement(state, a)
        self._extract(state)
        if new_domains:
            # The follow-up opens a NEW problem area (e.g. "he also threatened me" -> Criminal Law).
            # Ask its critical questions first, like a fresh intake, instead of answering with facts missing.
            # The new area gets its own question budget and one retrieval call of its own.
            state.questions_asked = 0
            state.retrieval_calls = min(state.retrieval_calls, MAX_RETRIEVAL_CALLS - 1)
            state.additional_asked = True  # skip the closing question; answer as soon as the facts are in
            nxt = self._ask_next(state, allow_additional=False)
            if nxt:
                return self._with_helplines(state, nxt, flags)
        return self._with_helplines(state, self._answer(state, latest_question=a.english), flags)

    def _add_statement(self, state: SessionState, a: TurnAnalysis) -> None:
        new = [d for d in a.domains if d not in state.domains]
        if new:
            state.domains += new
            state.checklist = ck.init_checklist(state.domains, state.sub_issues, state.checklist)
        state.case_statements_en.append(a.english)

    def _general(self, state: SessionState, a: TurnAnalysis) -> str:
        """Answer a question about the law (no personal case): fresh retrieval, same audit, no intake."""
        previous = state.case_statements_en[-2:] if state.mode == "general" else []  # context for follow-ups
        self._reset_case(state)
        state.mode, state.language_locked = "general", True
        state.domains = list(dict.fromkeys(a.domains))
        state.case_statements_en = previous + [a.english]
        return self._answer(state, latest_question=a.english if previous else None)

    def _start_case(self, state: SessionState, a: TurnAnalysis) -> str:
        state.mode = "case"
        state.language_locked = True
        state.domains = list(dict.fromkeys(a.domains))
        state.case_statements_en.append(a.english)
        state.checklist = ck.init_checklist(state.domains, state.sub_issues)
        self._extract(state)
        return self._ask_next(state)

    def _extract(self, state: SessionState) -> None:
        self._progress("Noting the facts of your case…")
        res = self.llm2.extract_facts(state.case_statements_en, state.domains, state.checklist,
                                      self.today, self._lang(state))
        for d, subs in (res.get("sub_issues") or {}).items():   # problem types only ever accumulate
            state.sub_issues[d] = list(dict.fromkeys(state.sub_issues.get(d, []) + subs))
        state.checklist = ck.init_checklist(state.domains, state.sub_issues, state.checklist)
        ck.apply_facts(state.checklist, res["facts"])
        self._suggested_question = res.get("question")
        if res["key_date"] and parse_date(res["key_date"]):
            state.key_date = res["key_date"]
        if res["amount_inr"]:
            state.amount_inr = res["amount_inr"]

    def _question_text(self, state: SessionState, group: str) -> str:
        """LLM 2's contextual phrasing if it targets the same topic the rule engine chose and is in the
        right script; otherwise the fixed question for that topic."""
        lang = self._lang(state)
        q = getattr(self, "_suggested_question", None)
        if q and q.get("group") == group:
            text = str(q.get("text", "")).strip()
            devanagari = bool(re.search(r"[ऀ-ॿ]", text))
            if 10 < len(text) < 450 and devanagari == (lang == "hi"):
                return text
        return group_question(group, lang)

    def _ask_next(self, state: SessionState, allow_additional: bool = True) -> str:
        lang = self._lang(state)
        g = ck.next_missing_group(state.checklist)
        if g and state.questions_asked < MAX_TOTAL_CLARIFICATIONS:
            state.status = "CLARIFYING"
            state.pending_field, state.pending_retries = g["first"], 0
            state.questions_asked += 1
            return self._question_text(state, g["group"])
        ck.mark_remaining_unresolved(state.checklist)
        state.pending_field = None
        if allow_additional and not state.additional_asked:
            state.status, state.additional_asked = "AWAITING_ADDITIONAL", True
            return closing_question(state.domains, lang)
        return ""

    def _clarification(self, state: SessionState, a: TurnAnalysis) -> str:
        lang = self._lang(state)
        status = a.clarification_status or ClarificationStatus.ANSWERED
        fid = state.pending_field
        if status == ClarificationStatus.ANSWERED:
            self._add_statement(state, a)
            self._extract(state)
            missing = ck.group_missing(state.checklist, fid)
            if missing == [fid]:  # single-fact question the validator says was answered
                ck.apply_facts(state.checklist, {fid: a.english})
            # several facts asked and some still missing -> _ask_next asks only those
        elif status == ClarificationStatus.PARTIALLY_ANSWERED:
            self._add_statement(state, a)
            self._extract(state)  # the rest of the topic is asked next, without "sorry"
        else:
            # Not an answer to THIS question — still keep every fact it contains
            # ("I don't remember the date, but he threatened me again") so other fields fill up.
            noted = bool(a.adds_case_info or [d for d in a.domains if d not in state.domains])
            if noted:
                self._add_statement(state, a)
                self._extract(state)
            missing = ck.group_missing(state.checklist, fid)
            # "Declined" is final only if the user actually SAID they don't know / won't say. A reply the
            # model labelled "declined" without such words ("he is chasing me") is treated as not answered.
            raw = state.transcript[-1]["display"] if state.transcript else ""
            said_so = f"{a.english or ''} {raw}".replace("’", "'")
            really_declined = status == ClarificationStatus.DECLINED and bool(EXPLICIT_DECLINE.search(said_so))
            if missing and not really_declined and state.pending_retries < MAX_CLARIFICATION_RETRIES:
                state.pending_retries += 1
                prefix = NOTED_PREFIX[lang] if noted else REPEAT_PREFIX[lang]
                return prefix + self._question_text(state, fid)
            ck.mark_unresolved(state.checklist, missing)  # clearly declined, or still unanswered after the repeats
        state.pending_field = None
        nxt = self._ask_next(state)
        return nxt or self._answer(state)

    # ------------------------------------------------------------------ answer
    def _retrieve(self, state: SessionState, queries: List[str], exclude: Optional[List[str]] = None) -> List[LegalDocument]:
        if state.retrieval_calls >= MAX_RETRIEVAL_CALLS:  # hard cap, enforced here in code
            state.retrieval_log.append({"blocked": True, "queries": queries})
            return []
        crim_date = parse_date(state.key_date) if "Criminal Law" in state.domains else None
        docs = self.kb.search(queries, state.domains, criminal_incident_date=crim_date, exclude=exclude)
        state.retrieval_calls += 1
        state.retrieval_log.append({"call": state.retrieval_calls, "queries": queries, "doc_ids": [d.doc_id for d in docs]})
        return docs

    def _facts_text(self, state: SessionState, facts: Dict) -> str:
        lines = list(state.case_statements_en) + [f"{k}: {v}" for k, v in facts.items()]
        if state.amount_inr:
            lines.append(f"Amount: {fmt_inr(state.amount_inr)}")
        return "\n".join(lines)

    def _answer(self, state: SessionState, latest_question: Optional[str] = None) -> str:
        lang = self._lang(state)
        state.status, state.pending_field, state.grounding_retries = "PROCESSING", None, 0
        state.answer, state.answer_en_md, state.removed_items = None, None, []  # never show a stale answer
        facts = ck.collected_facts(state.checklist)
        unresolved = ck.unresolved_labels(state.checklist)
        computed = compute_case_facts(state.domains, state.key_date, state.amount_inr, self.today)
        state.computed = computed

        # Retrieval call 1 (if budget remains); evidence accumulates across the consultation
        uncovered = [d for d in state.domains
                     if not any(self.kb.get(i) and d in self.kb.get(i).domains for i in state.evidence_ids)]
        if state.retrieval_calls < MAX_RETRIEVAL_CALLS and (not state.evidence_ids or latest_question or uncovered):
            self._progress("Finding the relevant law…")
            queries =self.llm2.search_queries(state.domains, facts, state.case_statements_en)
            queries.append(" ".join(state.case_statements_en)[-600:] + (f" {latest_question}" if latest_question else ""))
            docs = self._retrieve(state, queries, exclude=state.evidence_ids)
            state.evidence_ids += [d.doc_id for d in docs if d.doc_id not in state.evidence_ids]
        evidence = [self.kb.get(i) for i in state.evidence_ids if self.kb.get(i)]
        if not evidence:
            state.status = "ABSTAINED"
            return ABSTAIN_TEXT[lang]

        facts_text = self._facts_text(state, facts)
        computed_text = json.dumps(computed)
        kwargs = dict(domains=state.domains, statements_en=state.case_statements_en, facts=facts,
                      unresolved=unresolved, computed=computed, latest_question=latest_question,
                      general=state.mode == "general")

        self._progress(f"Drafting your answer from {len(evidence)} legal provisions…")
        draft = self.llm2.draft_answer(evidence=evidence, **kwargs)
        self._progress("Checking every point against the law (auditor)…")
        report = self.llm3.audit(draft, evidence, facts_text, computed_text)
        state.audit_reports.append({"attempt": 1, **report.model_dump(mode="json")})
        attempts = [(draft, report)]

        if report.status != GroundingStatus.PASS and not report.audit_error and state.grounding_retries < MAX_GROUNDING_RETRIES:
            state.grounding_retries += 1
            self._progress(f"Auditor flagged {len(report.failing_items) or 'some'} point(s) — correcting the draft…")
            if report.status == GroundingStatus.RETRIEVE_AGAIN and report.suggested_query:
                extra = self._retrieve(state, [report.suggested_query], exclude=state.evidence_ids)
                state.evidence_ids += [d.doc_id for d in extra]
                evidence = [self.kb.get(i) for i in state.evidence_ids if self.kb.get(i)]
            draft = self.llm2.draft_answer(evidence=evidence, feedback=report.feedback, **kwargs)
            report = self.llm3.audit(draft, evidence, facts_text, computed_text)
            state.audit_reports.append({"attempt": 2, **report.model_dump(mode="json")})
            attempts.append((draft, report))

        removed_note = ""
        if report.status != GroundingStatus.PASS:
            # Correction budget used up. Take the attempt with the fewest failing points, strip exactly
            # those points, re-check deterministically, and deliver only if real legal content remains.
            usable = [(d, r) for d, r in attempts if not r.audit_error]
            best = min(usable, key=lambda dr: len(dr[1].failing_items), default=None) if usable else None
            if usable:
                best = [dr for dr in usable if len(dr[1].failing_items) == len(best[1].failing_items)][-1]
            pruned = self._prune(best[0], best[1].failing_items) if best else None
            ev_map = {d.doc_id: {"act": d.act, "section": d.section, "text": d.text} for d in evidence}
            if pruned and pruned.get("legal_position") and pruned.get("options") and not run_deterministic_checks(
                    flatten_answer(pruned), ev_map, facts_text, computed_text):
                draft = pruned
                state.removed_items = best[1].failing_items
                removed_note = (f"{len(best[1].failing_items)} point(s) were removed because the auditor could not verify them "
                                f"against the law. Ask a lawyer about anything not covered here.")
            else:
                state.status = "ABSTAINED"
                return ABSTAIN_TEXT[lang]

        ev_dict = {d.doc_id: d for d in evidence}
        if state.mode == "general":
            referral = ["How this applies always depends on the exact facts. If it actually happens to you, or a "
                        "complaint or case is filed, speak to a lawyer."]
        else:
            referral = referral_reasons(state.domains, " ".join(state.case_statements_en), state.amount_inr,
                                        limitation_warning(state.domains, computed.get("months_elapsed")))
        md_en = render_answer(draft, ev_dict, referral, helpline_block(state.safety_flags, "en"), removed_note,
                              general=state.mode == "general")
        state.answer, state.answer_en_md, state.status = draft, md_en, "COMPLETED"
        return self._localise(state, md_en)

    @staticmethod
    def _prune(ans: Dict, failing: List[str]) -> Dict:
        bad = set(failing)
        out = dict(ans)
        for key, prefix in (("legal_position", "L"), ("options", "O"), ("deadlines", "D"), ("next_steps", "N"), ("assumptions", "A")):
            out[key] = [x for i, x in enumerate(ans.get(key) or [], 1) if f"{prefix}{i}" not in bad]
        if "S" in bad:
            out["summary"] = ""
        if "DOC" in bad:
            out["draft_document"] = {"type": "None", "text": ""}
        return out

    def _localise(self, state: SessionState, md_en: str) -> str:
        lang = self._lang(state)
        if lang == "en":
            return md_en
        # helplines are already rendered in English inside md_en; translate the whole answer once
        self._progress("Translating the verified answer…")
        try:
            tr = self.llm2.translate(md_en, lang)
        except LLMError:
            return TRANSLATION_NOTE[lang] + md_en
        if translation_preserves(md_en, tr):
            return TRANSLATION_NOTE[lang] + md_en
        return tr
