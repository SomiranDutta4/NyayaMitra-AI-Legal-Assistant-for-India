"""Scripted stand-in for the real LLM clients, so the pipeline can be tested offline.
It only tests plumbing (routing, limits, audit loop); real model quality is tested with live runs."""

import json
import re

from llm.client import UsageLog


class FakeClient:
    def __init__(self, role, usage: UsageLog, script=None):
        self.role, self.usage, self.script = role, usage, script or {}
        self.model = f"fake:{role}"

    def _log(self):
        self.usage.add(role=self.role, model=self.model, prompt_tokens=0, completion_tokens=0, ms=0)

    def chat(self, system, user, json_mode=False, max_tokens=0, temperature=0):
        self._log()
        return user  # translation: identity

    def chat_json(self, system, user, max_tokens=0):
        self._log()
        if "You are LLM 1" in system:
            msg = user.split("User's latest message:\n", 1)[1].strip().lower()
            ctx = json.loads(user.split("Conversation context: ", 1)[1].split("\n\nUser's latest")[0])
            pending = "pending_question" in ctx
            dom = []
            if any(w in msg for w in ("wife", "husband", "divorce")):
                dom.append("Family Law")
            if any(w in msg for w in ("deposit", "landlord", "rent")):
                dom.append("Property Law")
            if any(w in msg for w in ("threat", "beat", "chasing")):
                dom.append("Criminal Law")
            if any(w in msg for w in ("boss", "salary")):
                dom.append("Employment and Labour Law")
            if msg in ("hi", "hello"):
                return {"language": "en", "english": msg, "intent": "GREETING", "domains": [], "clarification_status": None, "reply": "Hello! Tell me your problem."}
            status = None
            if pending:
                status = "UNRELATED" if "what's up" in msg else ("DECLINED" if "don't know" in msg else "ANSWERED")
                status = self.script.get("force_status", status)
            if any(w in msg for w in ("thief", "defend", "stick")):
                dom.append("Criminal Law")
            intent = "ANSWER" if pending else ("FOLLOW_UP" if ctx.get("case_already_answered") else ("LEGAL_CASE" if dom else "VAGUE"))
            if not pending and (msg.startswith("can i") or "what does the law" in msg or "how to defend" in msg):
                intent = "GENERAL_QUESTION"
            if not pending and ("last night" in msg or "broke into" in msg):
                intent = "LEGAL_CASE"
            adds = len(msg.split()) > 5 and "what's up" not in msg
            return {"language": "en", "english": msg, "intent": intent, "domains": dom, "clarification_status": status,
                    "adds_case_info": adds, "reply": None if dom or pending else "What happened?"}
        if "intake form" in system:
            said = user.split("Everything the user has said so far (English):", 1)[1].lower()
            facts, subs = {}, {}
            if "wife" in said:
                facts["f_relationship"] = "User is the husband; other party is his wife"
                facts["f_situation"] = "Wife is leaving"
                subs["Family Law"] = ["spouse_left"]
            if "boss" in said:
                facts["l_status"] = "employed or formerly employed, given there is a boss"  # a guess: must be rejected
                subs["Employment and Labour Law"] = ["unpaid_salary"]
            amt = re.search(r"(\d{4,})", said)
            if "deposit" in said:
                facts.update({"p_role": "Tenant", "p_problem": "Deposit not returned",
                              "p_deduction_reason": "No reason given"})
                if amt:
                    facts["p_deposit_amount"] = amt.group(1)
                subs["Property Law"] = ["deposit"]
            if "pune" in said:
                facts["p_location"] = "Pune, Maharashtra"
            if "august" in said:
                facts["p_vacated"] = "August 2026"
            return {"sub_issues": subs, "facts": facts, "key_date": "2026-08-01",
                    "amount_inr": float(amt.group(1)) if amt else None, "question": self.script.get("question")}
        if "search queries" in system:
            return {"queries": ["security deposit refund", "restitution conjugal rights"]}
        if "experienced Indian lawyer" in system:
            ids = re.findall(r"^\[([A-Z0-9_]+)\]", user, re.M)
            bad = self.script.get("fabricate") and "AUDITOR REJECTED" not in user
            lp = [{"text": "You are entitled to the remedy in this provision.", "cites": [ids[0]]}]
            if bad or self.script.get("always_fabricate"):
                lp.append({"text": "You must act within 45 days under Section 999.", "cites": [ids[0]]})
            return {"summary": "You described a dispute.", "legal_position": lp,
                    "options": [{"title": "Send a notice", "detail": "Write to the other side.", "cites": [ids[0]]}],
                    "deadlines": [], "next_steps": ["Collect documents"], "evidence_to_collect": ["Receipts"],
                    "draft_document": {"type": "None", "text": ""}, "assumptions": []}
        if "independent auditor" in system:
            items = json.loads(user.split("STATEMENTS TO AUDIT:\n", 1)[1])
            return {"items": [{"id": i["id"], "verdict": "SUPPORTED", "reason": "ok"} for i in items],
                    "missing_law": False, "suggested_query": "", "overall_note": "ok"}
        raise AssertionError("unexpected prompt")


def factory(script=None):
    return lambda role, usage: FakeClient(role, usage, script)
