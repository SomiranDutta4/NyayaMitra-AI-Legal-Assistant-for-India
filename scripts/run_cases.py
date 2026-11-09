"""Run the test cases end-to-end against the real models and save raw outputs.

    python3 scripts/run_cases.py                 # all cases
    python3 scripts/run_cases.py 02 05           # only cases whose id starts with 02 or 05

Each case in tests/cases.json is a SIMULATED USER:
- "turns":   messages sent exactly as written (e.g. an off-topic reply to test the loop breaker);
- "answers": the facts this user knows, keyed by checklist field_id. Whenever NyayaMitra asks about a
             field, the simulated user answers from here (or says it doesn't know), so the script
             cannot fall out of step when the questions change;
- "closing": reply to the final "anything else / proof?" question (default "no");
- "auto":    "end" (default) = answer questions only after the last scripted turn,
             "each" = answer questions after every scripted turn (to test follow-ups).

Writes outputs/<case_id>.md (readable transcript + audit) and outputs/<case_id>.json (full state).
"""

import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from orchestrator.pipeline import NyayaMitraPipeline  # noqa: E402
from persistence.db import DatabaseManager  # noqa: E402

MAX_AUTO_REPLIES = 8
DONT_KNOW = {"en": "I'm not sure.", "hi": "मुझे पक्का नहीं पता।", "hinglish": "Mujhe pakka nahi pata."}


def converse(pipe, sid, case, md, state):
    """Answer NyayaMitra's pending questions from the simulated user's facts until it stops asking."""
    for _ in range(MAX_AUTO_REPLIES):
        if state is None or state.status not in ("CLARIFYING", "AWAITING_ADDITIONAL"):
            break
        if state.status == "AWAITING_ADDITIONAL":
            msg = case.get("closing", "no")
        else:
            lang = state.language_override or state.language
            msg = case.get("answers", {}).get(state.pending_field, DONT_KNOW.get(lang, DONT_KNOW["en"]))
        state, reply = pipe.handle(sid, msg)
        md += [f"**User:** {msg}", "", "**NyayaMitra:**", "", reply, "", "---", ""]
    return state


def main(prefixes):
    with open(os.path.join(ROOT, "tests", "cases.json"), encoding="utf-8") as f:
        cases = json.load(f)
    out_dir = os.path.join(ROOT, "outputs")
    os.makedirs(out_dir, exist_ok=True)
    pipe = NyayaMitraPipeline(DatabaseManager(os.path.join(out_dir, "runs.db")))
    for case in cases:
        if prefixes and not any(case["id"].startswith(p) for p in prefixes):
            continue
        sid = f"{case['id']}-{int(time.time())}"
        md = [f"# {case['id']}", f"_{case['note']}_", ""]
        t0 = time.time()
        state = None
        turns = case["turns"]
        for i, turn in enumerate(turns):
            state, reply = pipe.handle(sid, turn)
            md += [f"**User:** {turn}", "", "**NyayaMitra:**", "", reply, "", "---", ""]
            if case.get("auto", "end") == "each" or i == len(turns) - 1:
                state = converse(pipe, sid, case, md, state)
        md += ["## Pipeline record", f"- final status: `{state.status}`", f"- language: `{state.language}`",
               f"- domains: {state.domains}", f"- problem types: {state.sub_issues}",
               f"- questions asked: {state.questions_asked}",
               f"- retrieval calls: {state.retrieval_calls}", f"- evidence: {state.evidence_ids}",
               f"- model calls: {len(state.usage)}, tokens in/out: "
               f"{sum(c.get('prompt_tokens', 0) for c in state.usage)}/{sum(c.get('completion_tokens', 0) for c in state.usage)}",
               f"- wall time: {time.time() - t0:.0f}s", ""]
        md.append("### Checklist")
        md += [f"- {f['label']}: {f['status']}" + (f" — {f['value']}" if f.get("value") else "")
               for f in state.checklist.values()]
        md.append("")
        for r in state.audit_reports:
            md.append(f"### Audit attempt {r['attempt']}: {r['status']}")
            md += [f"- L1 [{d['item']}] {d['check']}: {d['detail']}" for d in r.get("deterministic_issues", [])]
            md += [f"- L2 [{x.get('id')}] {x.get('verdict')}: {x.get('reason', '')}" for x in r.get("semantic_results", [])]
            if r.get("audit_error"):
                md.append(f"- audit error: {r['audit_error']}")
        if state.last_error:
            md.append(f"\n**Last error:** {state.last_error}")
        with open(os.path.join(out_dir, f"{case['id']}.md"), "w", encoding="utf-8") as f:
            f.write("\n".join(md))
        with open(os.path.join(out_dir, f"{case['id']}.json"), "w", encoding="utf-8") as f:
            f.write(state.model_dump_json(indent=1))
        print(f"{case['id']}: {state.status} | questions={state.questions_asked} | calls={len(state.usage)} | "
              f"{time.time() - t0:.0f}s", flush=True)


if __name__ == "__main__":
    main(sys.argv[1:])
