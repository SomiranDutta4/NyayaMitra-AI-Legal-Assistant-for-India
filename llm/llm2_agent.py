"""LLM 2: Main legal agent. Works only in English.

- extract_facts:   detects the type of problem, fills checklist fields with SPECIFIC facts only, and
                   phrases the next question in context (same call, no extra API cost)
- search_queries:  turns the facts into English Bare-Act search queries
- draft_answer:    writes the structured answer, every legal statement tied to a doc_id
- translate:       English answer -> user's language (separate 'translate' model role)
"""

import json
from datetime import date
from typing import Any, Dict, List, Optional

from kb.retriever import LegalDocument
from llm.client import LLMClient

# ------------------------------------------------------------------ facts
FACTS_SYSTEM = """You run the intake form of an Indian legal-aid assistant. Everything you read is in English.

STEP 1 — PROBLEM TYPES. For each domain, pick the problem type(s) from PROBLEM TYPES that the user has described
(one or more). If none is clear yet, return [] for that domain.

STEP 2 — FACTS. Fill a field ONLY with a SPECIFIC fact the user stated, or one that is CERTAIN from their words.
- Certain:   "my wife is leaving me" -> relationship: "User is the husband; the other party is his wife".
- A described event IS a fact: "someone called pretending to be my bank and I lost money on UPI" ->
  incident: "Caller impersonating the bank; money lost via UPI; caller unknown" (but amount and date stay null).
- NOT facts: "my boss is not giving me money" does NOT tell employment status (still working? fired?) or what is unpaid
  (which months? how much?) -> those fields stay null.
- Never write hedged or generic values ("probably", "given that...", "employed or formerly employed", "some money",
  "money owed"). If you would need to hedge, the value is null.
- A field marked UNRESOLVED was declined by the user: keep it null unless they have now given it.
Write short values from the user's point of view, keeping amounts and dates exactly.
Also return key_date (main event / cause of action, "YYYY-MM-DD" or "YYYY-MM"; resolve "2 months ago" using today's date)
and amount_inr (main amount in rupees as a number), else null.

STEP 3 — NEXT QUESTION. Consider critical fields that apply to the problem types you found (applies_to empty = always),
that are still empty after STEP 2 and are not UNRESOLVED. Take ONLY the FIRST such field in the list order.
Write ONE short, warm question about that single fact (never combine it with other facts), in {language}:
- refer briefly to what the user already said; never ask for something they already told you;
- plain everyday words, no legal advice and no section numbers;
- if a fact decides a deadline, the court or the law, add a few words in brackets saying why;
- for dates, say a rough date or month is fine.
If no such field remains, "question" is null.

Return ONLY JSON:
{"sub_issues": {"<domain>": ["<type>"]}, "facts": {"<field_id>": "value or null"},
 "key_date": "...|null", "amount_inr": number|null, "question": {"field_id": "<field_id>", "text": "..."} | null}"""
LANG_NAMES = {"en": "English", "hi": "Hindi in Devanagari script", "hinglish": "Hinglish (Hindi in Roman script)"}

QUERY_SYSTEM = """You turn a legal-aid case into search queries for an index of Indian Bare Act provisions (English).
Write 2 short queries using plain legal terms a statute would use (e.g. "security deposit refund tenant landlord",
"recover possession dispossessed", "deficiency in service refund compensation consumer complaint", "wages not paid claim authority").
Return ONLY JSON: {"queries": ["...", "..."]}"""

DRAFT_SYSTEM = """You are NyayaMitra, an experienced Indian lawyer explaining a person's legal position to them in plain English.
You give LEGAL INFORMATION grounded ONLY in the EVIDENCE provisions provided. You are not their advocate.

HARD RULES (an automated auditor will reject violations):
1. Every item in legal_position, options and deadlines MUST cite at least one doc_id from EVIDENCE in "cites".
2. Every number (amount, days, months, years, %) in a cited item must appear in the provisions it cites,
   in the user's facts, or in SYSTEM-COMPUTED FACTS. Never invent time limits, fees or penalties.
3. Name only Acts that appear in EVIDENCE. Never cite case law or judgments. Never mention a section that is not in EVIDENCE.
4. If the evidence does not cover something important, say so in "assumptions" instead of guessing.
5. Use SYSTEM-COMPUTED FACTS as given (time elapsed, which criminal code applies, which consumer forum),
   and cite the EVIDENCE provision behind them (e.g. the money-limit rules for the consumer forum).
6. If a provision says it applies only in some states (e.g. Model Tenancy Act), say that clearly.
7. Facts marked UNRESOLVED were not provided: state the assumption you make, or give the answer conditionally.
8. Speak directly to the person ("you"), calm and practical. No legal jargon without a one-line explanation.
9. Never assume facts in the user's favour that they did not state; phrase them as conditions
   ("if she left without a reasonable excuse, ..."). Do not invent dates; use the dates exactly as given.
10. If the user names a law or section that is NOT in EVIDENCE, do not repeat its claimed content as true;
    say in "assumptions" that you could not verify it (e.g. "I could not find any 'Section 420B' giving triple
    compensation in the law I checked") and explain what the evidence actually provides.

Return ONLY JSON with this shape:
{
 "summary": "2-3 sentences restating their situation as you understand it",
 "legal_position": [{"text": "where they stand legally, one point per item", "cites": ["DOC_ID"]}],
 "options": [{"title": "short name of the remedy/route", "detail": "what it is, where to go, what it can get them", "cites": ["DOC_ID"]}],
 "deadlines": [{"text": "time limit and from when it runs", "cites": ["DOC_ID"]}],
 "next_steps": ["ordered practical steps for the next 1-2 weeks"],
 "evidence_to_collect": ["documents / proof to keep ready"],
 "draft_document": {"type": "Legal notice | Consumer complaint summary | Police complaint | Wage claim application | None", "text": "short ready-to-edit draft (max 220 words) with [placeholders] for names/addresses; only facts the user gave"},
 "assumptions": ["assumptions made / gaps in the evidence"]
}
Keep it tight: 2-5 legal_position items, 2-4 options, 1-3 deadlines, 3-6 next_steps."""

TRANSLATE_SYSTEM = """Translate the following legal-information answer from English into {target}.
Rules:
- Keep the Markdown structure exactly (headings, bullets, bold, blockquotes, numbering).
- Keep every number in Western digits exactly as written (amounts, days, years, dates, section numbers).
- Keep citation markers like [1], [2] exactly where they are.
- Keep Act names and "Section ..." references in English exactly as written (you may add a short explanation in brackets).
- Keep placeholders like [Your Name] as they are.
- Use simple, everyday words a common person understands.
Return ONLY the translated text."""
TARGETS = {"hi": "Hindi written in Devanagari script", "hinglish": "Hinglish (Hindi written in Roman/Latin script, mixed with common English words)"}


def format_evidence(docs: List[LegalDocument]) -> str:
    return "\n\n".join(f"[{d.doc_id}] {d.section}, {d.act} — {d.title}\n{d.text}" for d in docs)


class LLM2Agent:
    def __init__(self, client: LLMClient, translator: Optional[LLMClient] = None):
        self.llm = client
        self.translator = translator

    def extract_facts(self, statements_en: List[str], domains: List[str], checklist: Dict[str, Dict],
                      today: Optional[date] = None, lang: str = "en") -> Dict[str, Any]:
        from checklists.definitions import DOMAIN_CHECKLISTS, SUB_ISSUES
        fields = []
        for d in domains:  # every field of the domain, so a newly detected problem type can be filled at once
            for f in DOMAIN_CHECKLISTS.get(d, []):
                status = (checklist.get(f.field_id) or {}).get("status", "MISSING")
                fields.append({"field_id": f.field_id, "domain": d, "label": f.label, "description": f.description,
                               "category": f.category, "applies_to": f.applies_to or [],
                               "status": status, "current_value": (checklist.get(f.field_id) or {}).get("value")})
        types = {d: SUB_ISSUES.get(d, {}) for d in domains}
        user = (f"Today's date: {(today or date.today()).isoformat()}\n\n"
                f"PROBLEM TYPES:\n{json.dumps(types, indent=1)}\n\n"
                f"CHECKLIST (in priority order):\n{json.dumps(fields, indent=1, ensure_ascii=False)}\n\n"
                f"Everything the user has said so far (English):\n" + "\n".join(f"- {s}" for s in statements_en))
        system = FACTS_SYSTEM.replace("{language}", LANG_NAMES.get(lang, "English"))
        data = self.llm.chat_json(system, user, max_tokens=1400)
        facts = data.get("facts") or {}
        amt = data.get("amount_inr")
        try:
            amt = float(str(amt).replace(",", "")) if amt not in (None, "", "null") else None
        except ValueError:
            amt = None
        kd = data.get("key_date")
        subs_raw = data.get("sub_issues") or {}
        subs = {d: [s for s in (subs_raw.get(d) or []) if s in SUB_ISSUES.get(d, {})] for d in domains} \
            if isinstance(subs_raw, dict) else {}
        q = data.get("question")
        if isinstance(q, dict) and q.get("text") and (q.get("field_id") or q.get("group")):
            q = {"group": q.get("field_id") or q.get("group"), "text": q["text"]}  # each field is its own group
        else:
            q = None
        return {"facts": facts if isinstance(facts, dict) else {}, "key_date": kd if isinstance(kd, str) else None,
                "amount_inr": amt, "sub_issues": subs, "question": q}

    def search_queries(self, domains: List[str], facts: Dict[str, str], statements_en: List[str]) -> List[str]:
        user = (f"Domains: {domains}\nFacts: {json.dumps(facts, ensure_ascii=False)}\n"
                f"User's words: {' '.join(statements_en)[:1500]}")
        try:
            q = self.llm.chat_json(QUERY_SYSTEM, user, max_tokens=300).get("queries") or []
            return [str(x) for x in q if str(x).strip()][:3]
        except Exception:
            return []

    def draft_answer(self, *, domains, statements_en, facts, unresolved, computed, evidence: List[LegalDocument],
                     feedback: Optional[str] = None, latest_question: Optional[str] = None,
                     general: bool = False) -> Dict[str, Any]:
        parts = [
            f"DOMAINS: {', '.join(domains)}",
            "USER'S OWN WORDS (English):\n" + "\n".join(f"- {s}" for s in statements_en),
            "COLLECTED FACTS:\n" + json.dumps(facts, indent=1, ensure_ascii=False),
            "UNRESOLVED FACTS (user did not provide): " + (", ".join(unresolved) or "none"),
            "SYSTEM-COMPUTED FACTS (use as given):\n" + json.dumps(computed, indent=1, ensure_ascii=False),
            "EVIDENCE (the only law you may rely on):\n" + format_evidence(evidence),
        ]
        if latest_question:
            parts.append(f"THE USER'S LATEST FOLLOW-UP (answer it within the structure): {latest_question}")
        if general:
            parts.append(
                "MODE: GENERAL QUESTION. The user is asking what the law says (in general or for a possible situation),\n"
                "not describing something that happened to them. So:\n"
                "- summary: restate the question in one or two sentences; do not invent facts about the user;\n"
                "- legal_position: what the law says, including its limits and conditions;\n"
                "- options: what this means in practice / what a person in that situation can do;\n"
                "- deadlines: only if the evidence gives one that matters for this question, else [];\n"
                "- next_steps: practical, general steps; evidence_to_collect: only if useful, else [];\n"
                "- draft_document: {\"type\": \"None\", \"text\": \"\"};\n"
                "- assumptions: say that the answer is general and depends on the exact facts.")
        if feedback:
            parts.append("AUDITOR REJECTED YOUR PREVIOUS DRAFT. Fix every issue below (remove a point if it cannot be supported):\n" + feedback)
        return self.llm.chat_json(DRAFT_SYSTEM, "\n\n".join(parts), max_tokens=3000)

    def translate(self, markdown_en: str, lang: str) -> str:
        if lang not in TARGETS or not self.translator:
            return markdown_en
        return self.translator.chat(TRANSLATE_SYSTEM.format(target=TARGETS[lang]), markdown_en,
                                    max_tokens=8000, temperature=0.2)
