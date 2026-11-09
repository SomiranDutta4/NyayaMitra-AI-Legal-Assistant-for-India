"""Deterministic checklist rule engine (no model calls).

- Only fields that apply to the detected type of problem are in the checklist.
- Missing critical fields are asked ONE AT A TIME, in priority order.
- Guessed / hedged values are rejected in code, so a vague phrase can never tick a critical box.
"""

import re
from typing import Any, Dict, List, Optional

from checklists.definitions import DOMAIN_CHECKLISTS

_EMPTY = {"", "null", "none", "unknown", "not mentioned", "not stated", "not specified", "unspecified",
          "n/a", "na", "not provided", "not given", "unclear"}
# A value that hedges is a guess, not a fact ("Employed or formerly employed, given there is a boss").
_HEDGE = re.compile(
    r"\b(probably|possibly|presumably|likely|maybe|perhaps|assum\w*|implied|implies|inferred|"
    r"given (that|there)|not (clear|specified|mentioned|stated)|unclear|unspecified|some money|or formerly)\b", re.I)


def is_real_value(val: Any) -> bool:
    if val is None:
        return False
    s = str(val).strip()
    return bool(s) and s.lower().strip(" .") not in _EMPTY and not _HEDGE.search(s)


def _applies(field, subs: List[str]) -> bool:
    return field.applies_to is None or bool(set(field.applies_to) & set(subs or []))


def init_checklist(domains: List[str], sub_issues: Optional[Dict[str, List[str]]] = None,
                   existing: Optional[Dict[str, Dict]] = None) -> Dict[str, Dict[str, Any]]:
    """(Re)build the checklist for these domains and problem types, keeping collected values.
    A MISSING field that no longer applies (problem type changed) is dropped."""
    sub_issues = sub_issues or {}
    old = dict(existing or {})
    state: Dict[str, Dict[str, Any]] = {}
    for d in domains:
        for f in DOMAIN_CHECKLISTS.get(d, []):
            if f.field_id in state:
                continue
            prev = old.get(f.field_id)
            if _applies(f, sub_issues.get(d, [])) or (prev and prev["status"] != "MISSING"):
                state[f.field_id] = prev or {
                    "field_id": f.field_id, "domain": d, "label": f.label, "category": f.category,
                    "description": f.description, "group": f.group, "status": "MISSING", "value": None,
                }
    return state


def apply_facts(checklist: Dict[str, Dict], facts: Dict[str, Any]) -> None:
    for fid, val in (facts or {}).items():
        if fid in checklist and checklist[fid]["status"] != "COLLECTED" and is_real_value(val):
            checklist[fid]["status"] = "COLLECTED"
            checklist[fid]["value"] = str(val).strip()


def next_missing_group(checklist: Dict[str, Dict]) -> Optional[Dict[str, Any]]:
    """The single next question: the first critical MISSING field in priority order (one fact per turn)."""
    first = next((f for f in checklist.values() if f["category"] == "critical" and f["status"] == "MISSING"), None)
    if not first:
        return None
    return {"group": first["field_id"], "field_ids": [first["field_id"]], "first": first["field_id"]}


def group_missing(checklist: Dict[str, Dict], field_id: Optional[str]) -> List[str]:
    """[field_id] if the asked field is still MISSING, else []."""
    f = checklist.get(field_id) if field_id else None
    return [field_id] if f and f["category"] == "critical" and f["status"] == "MISSING" else []


def mark_unresolved(checklist: Dict[str, Dict], field_ids: List[str]) -> None:
    for fid in field_ids:
        if fid in checklist and checklist[fid]["status"] == "MISSING":
            checklist[fid]["status"] = "UNRESOLVED"


def mark_remaining_unresolved(checklist: Dict[str, Dict]) -> None:
    for f in checklist.values():
        if f["category"] == "critical" and f["status"] == "MISSING":
            f["status"] = "UNRESOLVED"


def collected_facts(checklist: Dict[str, Dict]) -> Dict[str, str]:
    return {f["label"]: f["value"] for f in checklist.values() if f["status"] == "COLLECTED"}


def unresolved_labels(checklist: Dict[str, Dict]) -> List[str]:
    return [f["label"] for f in checklist.values() if f["category"] == "critical" and f["status"] == "UNRESOLVED"]
