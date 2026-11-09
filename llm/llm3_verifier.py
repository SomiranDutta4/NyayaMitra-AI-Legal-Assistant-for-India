"""LLM 3: Independent grounding auditor.

Layer 1 (deterministic, verification/checks.py): citations, sections, Act names, numbers.
Layer 2 (semantic, a different model from the drafter): is each statement actually supported
by the provision it cites?
Fails CLOSED: if the audit itself cannot run, the answer is not delivered as verified.
"""

import json
from typing import Any, Dict, List

from pydantic import BaseModel, Field

from config.settings import GroundingStatus
from kb.retriever import LegalDocument
from llm.client import LLMClient
from llm.llm2_agent import format_evidence
from verification.checks import run_deterministic_checks


class VerificationReport(BaseModel):
    status: GroundingStatus
    deterministic_issues: List[Dict[str, Any]] = Field(default_factory=list)
    semantic_results: List[Dict[str, Any]] = Field(default_factory=list)
    failing_items: List[str] = Field(default_factory=list)
    feedback: str = ""
    suggested_query: str = ""
    audit_error: str = ""


def flatten_answer(ans: Dict[str, Any]) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    if ans.get("summary"):
        items.append({"id": "S", "kind": "summary", "text": str(ans["summary"]), "cites": []})
    for i, x in enumerate(ans.get("legal_position") or [], 1):
        items.append({"id": f"L{i}", "kind": "legal_position", "text": str(x.get("text", "")), "cites": list(x.get("cites") or [])})
    for i, x in enumerate(ans.get("options") or [], 1):
        items.append({"id": f"O{i}", "kind": "option", "text": f"{x.get('title', '')}: {x.get('detail', '')}", "cites": list(x.get("cites") or [])})
    for i, x in enumerate(ans.get("deadlines") or [], 1):
        items.append({"id": f"D{i}", "kind": "deadline", "text": str(x.get("text", "")), "cites": list(x.get("cites") or [])})
    for i, x in enumerate(ans.get("next_steps") or [], 1):
        items.append({"id": f"N{i}", "kind": "next_step", "text": str(x), "cites": []})
    for i, x in enumerate(ans.get("assumptions") or [], 1):
        items.append({"id": f"A{i}", "kind": "assumption", "text": str(x), "cites": []})
    doc = ans.get("draft_document") or {}
    if isinstance(doc, dict) and doc.get("text") and str(doc.get("type", "None")).lower() != "none":
        items.append({"id": "DOC", "kind": "draft_document", "text": str(doc["text"]), "cites": []})
    return items


SEMANTIC_SYSTEM = """You are LLM 3, an independent auditor for an Indian legal-information assistant.
Check each numbered statement against the EVIDENCE (summaries of Bare Act provisions) and the user's FACTS.

Mark an item UNSUPPORTED if it:
- states a legal rule, right, remedy, penalty, forum, procedure or time limit that the cited provisions do not say
  (for items with no citations, that NO evidence provision says), or misstates/overstates it;
- applies a provision to facts it clearly does not fit (e.g. a state-specific law presented as applying everywhere);
- contradicts the user's facts.
Practical advice that makes no legal claim (keep receipts, send an email, visit the office) is SUPPORTED.
Fair paraphrase is fine; do not be pedantic about wording.

Also say whether an obviously essential provision is MISSING from the evidence for this case
(e.g. no limitation period, no forum) and suggest one English search query to find it.

Return ONLY JSON:
{"items": [{"id": "L1", "verdict": "SUPPORTED|UNSUPPORTED", "reason": "short"}],
 "missing_law": true|false, "suggested_query": "...", "overall_note": "short"}"""


class LLM3Auditor:
    def __init__(self, client: LLMClient):
        self.llm = client

    def _semantic(self, items, evidence: List[LegalDocument], facts_text: str) -> Dict[str, Any]:
        audit_items = [{"id": i["id"], "text": i["text"], "cites": i["cites"]}
                       for i in items if i["kind"] in ("summary", "legal_position", "option", "deadline", "next_step")]
        user = (f"EVIDENCE:\n{format_evidence(evidence)}\n\nUSER FACTS:\n{facts_text}\n\n"
                f"STATEMENTS TO AUDIT:\n{json.dumps(audit_items, indent=1, ensure_ascii=False)}")
        return self.llm.chat_json(SEMANTIC_SYSTEM, user, max_tokens=1800)

    def audit(self, answer: Dict[str, Any], evidence: List[LegalDocument], facts_text: str,
              computed_text: str) -> VerificationReport:
        items = flatten_answer(answer)
        ev = {d.doc_id: {"act": d.act, "section": d.section, "text": d.text} for d in evidence}
        det = run_deterministic_checks(items, ev, facts_text, computed_text)

        if not any(i["kind"] == "legal_position" for i in items):
            det.append({"item": "-", "check": "structure", "detail": "No legal_position items were produced."})

        try:
            sem = self._semantic(items, evidence, f"{facts_text}\nSYSTEM-COMPUTED FACTS (reliable): {computed_text}")
            sem_items = [x for x in sem.get("items", []) if isinstance(x, dict)]
        except Exception as e:  # fail closed
            return VerificationReport(status=GroundingStatus.ABSTAIN, deterministic_issues=det,
                                      audit_error=f"Semantic audit could not run: {e}",
                                      feedback="Audit unavailable; answer not verified.")

        unsupported = [x for x in sem_items if str(x.get("verdict", "")).upper() != "SUPPORTED"]
        failing = sorted({d["item"] for d in det if d["item"] != "-"} | {str(x.get("id")) for x in unsupported})

        lines = [f"- [{d['item']}] {d['check']}: {d['detail']}" for d in det]
        lines += [f"- [{x.get('id')}] unsupported: {x.get('reason', '')}" for x in unsupported]
        if not lines:
            status = GroundingStatus.PASS
        elif sem.get("missing_law") and sem.get("suggested_query"):
            status = GroundingStatus.RETRIEVE_AGAIN
        else:
            status = GroundingStatus.REVISE
        return VerificationReport(status=status, deterministic_issues=det, semantic_results=sem_items,
                                  failing_items=failing, feedback="\n".join(lines),
                                  suggested_query=str(sem.get("suggested_query") or ""))
