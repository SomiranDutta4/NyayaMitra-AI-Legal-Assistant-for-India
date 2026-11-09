"""Offline tests: deterministic checks + full pipeline plumbing with a scripted fake LLM."""

import os
import sys
from datetime import date

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.settings import MAX_RETRIEVAL_CALLS  # noqa: E402
from kb.retriever import get_kb  # noqa: E402
from orchestrator.pipeline import NyayaMitraPipeline  # noqa: E402
from persistence.db import DatabaseManager  # noqa: E402
from rules.legal_rules import compute_case_facts, consumer_forum  # noqa: E402
from rules.safety import detect_safety_flags, helpline_block  # noqa: E402
from tests.fake_llm import factory  # noqa: E402
from verification.checks import extract_numbers, run_deterministic_checks, translation_preserves  # noqa: E402


# ------------------------------------------------------------ deterministic checks
def ev(*ids):
    kb = get_kb()
    return {i: {"act": kb.get(i).act, "section": kb.get(i).section, "text": kb.get(i).text} for i in ids}


def test_numbers_words_and_digits_match():
    assert ("month", 24.0) in extract_numbers("within two years")
    assert ("month", 24.0) in extract_numbers("within 2 years")
    assert ("inr", 5_000_000.0) in extract_numbers("up to ₹50 lakh")
    assert ("inr", 5_000_000.0) in extract_numbers("fifty lakh rupees")
    assert ("day", 2.0) in extract_numbers("within two working days")
    assert ("hour", 48.0) in extract_numbers("within forty-eight hours")


def test_invented_number_is_caught():
    items = [{"id": "L1", "kind": "legal_position", "text": "File within 30 days.", "cites": ["CPA2019_S69"]}]
    issues = run_deterministic_checks(items, ev("CPA2019_S69"), "", "")
    assert any(i["check"] == "number" for i in issues)


def test_correct_number_passes():
    items = [{"id": "L1", "kind": "legal_position", "text": "You have 2 years to file (Section 69).", "cites": ["CPA2019_S69"]}]
    assert run_deterministic_checks(items, ev("CPA2019_S69"), "", "") == []


def test_outdated_limit_caught():
    items = [{"id": "L1", "kind": "legal_position", "text": "District Commission hears claims up to ₹1 crore.", "cites": ["CPJR2021_R3_5"]}]
    assert any(i["check"] == "number" for i in run_deterministic_checks(items, ev("CPJR2021_R3_5"), "", ""))


def test_fake_citation_and_section_and_act_caught():
    items = [{"id": "L1", "kind": "legal_position", "text": "Under Section 420 IPC he is liable.", "cites": ["FAKE_ID"]}]
    checks = {i["check"] for i in run_deterministic_checks(items, ev("BNS2023_S318"), "", "")}
    assert {"citation", "section", "act"} <= checks


def test_uncited_legal_statement_caught():
    items = [{"id": "O1", "kind": "option", "text": "Go to court", "cites": []}]
    assert run_deterministic_checks(items, ev("CPA2019_S35"), "", "")


def test_user_amount_allowed():
    items = [{"id": "L1", "kind": "legal_position", "text": "Your ₹40,000 deposit must be refunded.", "cites": ["MTA2021_S11"]}]
    assert run_deterministic_checks(items, ev("MTA2021_S11"), "deposit of Rs 40000", "") == []


def test_translation_check():
    assert translation_preserves("within 2 years [1]", "2 साल के भीतर [1]") == []
    assert translation_preserves("within 2 years [1]", "दो साल के भीतर") != []


# ------------------------------------------------------------ rules
def test_safety_flags():
    assert "danger" in detect_safety_flags("hi i am in danger")
    assert "danger" in detect_safety_flags("mujhe jaan se maar denge")
    assert "danger" in detect_safety_flags("मुझे बचाओ")
    assert detect_safety_flags("my landlord kept my deposit") == []
    assert "**112**" in helpline_block(["danger"], "hi")


def test_legal_rules():
    assert consumer_forum(45000).startswith("District")
    assert consumer_forum(6_000_000).startswith("State")
    c = compute_case_facts(["Criminal Law"], "2024-05-10", None, today=date(2026, 11, 9))
    assert "Indian Penal Code" in c["criminal_code"]
    c = compute_case_facts(["Criminal Law"], "2025-01-10", None, today=date(2026, 11, 9))
    assert "Bharatiya Nyaya Sanhita" in c["criminal_code"]


def test_retrieval_era_filter_and_domain():
    kb = get_kb()
    old = [d.act for d in kb.search(["cheating fraud"], ["Criminal Law"], criminal_incident_date=date(2024, 1, 1))]
    new = [d.act for d in kb.search(["cheating fraud"], ["Criminal Law"], criminal_incident_date=date(2025, 1, 1))]
    assert any("Indian Penal Code" in a for a in old) and not any("Nyaya Sanhita" in a for a in old if "Repeal" not in a)
    assert any("Nyaya Sanhita" in a for a in new) and not any("Indian Penal Code" in a for a in new)
    deposit = [d.doc_id for d in kb.search(["security deposit refund landlord"], ["Property Law"])]
    assert deposit[0] == "MTA2021_S11"


# ------------------------------------------------------------ pipeline plumbing
DEPOSIT_FLOW = ["landlord is not returning my deposit of 40000", "Pune", "i vacated in august", "no"]
@pytest.fixture
def db(tmp_path):
    return DatabaseManager(str(tmp_path / "t.db"))


def run(p, sid, msgs):
    out = []
    for m in msgs:
        st, r = p.handle(sid, m)
        out.append(r)
    return st, out


def test_prefill_from_first_message(db):
    """'my wife is leaving me' must NOT trigger a question about the relationship."""
    p = NyayaMitraPipeline(db, factory(), today=date(2026, 11, 9))
    st, out = run(p, "s1", ["hi", "my wife is leaving me"])
    assert st.checklist["f_relationship"]["status"] == "COLLECTED"
    assert st.pending_field != "f_relationship"
    assert "relation" not in out[-1].lower()


def test_unrelated_reply_repeats_once_then_moves_on(db):
    p = NyayaMitraPipeline(db, factory(), today=date(2026, 11, 9))
    from config.settings import MAX_CLARIFICATION_RETRIES
    st, out = run(p, "s2", ["my wife is leaving me", "hello bhai what's up"])
    assert out[-1].startswith("Just so I can help you properly")
    first = st.pending_field
    st, out = run(p, "s2", ["hello bhai what's up"] * MAX_CLARIFICATION_RETRIES)  # repeats used up -> move on
    assert st.checklist[first]["status"] == "UNRESOLVED"


def test_non_answer_with_useful_facts_is_saved(db):
    """'I don't know the date, but he threatened me…' does not answer the question, but its facts must be kept."""
    p = NyayaMitraPipeline(db, factory(), today=date(2026, 11, 9))
    st, _ = run(p, "na1", ["landlord is not returning my deposit of 40000"])
    asked = st.pending_field
    msg = "i don't know exactly, but he also threatened to beat me yesterday"
    st, _ = run(p, "na1", [msg])
    assert msg in st.case_statements_en             # saved for extraction and the drafter
    assert "Criminal Law" in st.domains             # new domain picked up from the extra info
    assert st.checklist[asked]["status"] == "UNRESOLVED"  # declined field is not re-asked forever


def test_pure_small_talk_is_not_saved(db):
    p = NyayaMitraPipeline(db, factory(), today=date(2026, 11, 9))
    st, _ = run(p, "na2", ["my wife is leaving me", "hello bhai what's up"])
    assert "hello bhai what's up" not in st.case_statements_en


def test_full_flow_reaches_verified_answer(db):
    p = NyayaMitraPipeline(db, factory(), today=date(2026, 11, 9))
    st, out = run(p, "s3", DEPOSIT_FLOW)
    assert st.status == "COMPLETED", out[-1]
    assert "Sources" in out[-1] and "15100" in out[-1]
    assert st.retrieval_calls <= MAX_RETRIEVAL_CALLS


def test_fabrication_is_corrected_by_one_retry(db):
    p = NyayaMitraPipeline(db, factory({"fabricate": True}), today=date(2026, 11, 9))
    st, out = run(p, "s4", DEPOSIT_FLOW)
    assert len(st.audit_reports) == 2 and st.audit_reports[0]["status"] != "PASS"
    assert st.status == "COMPLETED" and "999" not in out[-1]


def test_persistent_fabrication_is_pruned_not_shown(db):
    p = NyayaMitraPipeline(db, factory({"always_fabricate": True}), today=date(2026, 11, 9))
    st, out = run(p, "s5", DEPOSIT_FLOW)
    assert "999" not in out[-1]
    assert st.status in ("COMPLETED", "ABSTAINED")


def test_lockout_retrieves_dispossession_section():
    from datetime import date as _d
    ids = [d.doc_id for d in get_kb().search(["landlord locked my room and kept my laptop, threatened to beat me"],
                                             ["Property Law", "Criminal Law"], criminal_incident_date=_d(2026, 11, 1))]
    assert "SRA1963_S6" in ids and "BNS2023_S351" in ids


def _failing_draft_factory():
    """Fake LLM whose drafter fails once with a provider error, then works."""
    from llm.client import LLMError
    from tests.fake_llm import FakeClient
    calls = {"n": 0}

    class Flaky(FakeClient):
        def chat_json(self, system, user, max_tokens=0):
            if "experienced Indian lawyer" in system and calls["n"] == 0:
                calls["n"] += 1
                raise LLMError("429 rate limit")
            return super().chat_json(system, user, max_tokens)
    return lambda role, usage: Flaky(role, usage)


def test_error_then_retry_does_not_pollute_facts(db):
    p = NyayaMitraPipeline(db, _failing_draft_factory(), today=date(2026, 11, 9))
    st, out = run(p, "e1", DEPOSIT_FLOW)
    assert st.status == "ERROR" and "rate limit" in (st.last_error or "")
    n_before = len(st.case_statements_en)
    st, out = run(p, "e1", ["retry"])
    assert st.status == "COMPLETED"
    assert len(st.case_statements_en) == n_before  # "retry" was not added as a fact


def test_translation_fallback_shows_english_with_note(db):
    from tests.fake_llm import FakeClient

    class BadTranslator(FakeClient):
        def chat(self, system, user, **kw):
            return "अनुवाद जिसमें कोई अंक नहीं है"  # lost every number -> must not be shown
    f = lambda role, usage: (BadTranslator if role == "translate" else FakeClient)(role, usage)
    p = NyayaMitraPipeline(db, f, today=date(2026, 11, 9))
    st, out = None, None
    for m in DEPOSIT_FLOW:
        st, out = p.handle("t1", m, language_override="hi")
    assert st.status == "COMPLETED"
    assert out.startswith("_(") and "Sources" in out  # English answer with Hindi note


def test_language_override_questions(db):
    p = NyayaMitraPipeline(db, factory(), today=date(2026, 11, 9))
    st, out = p.handle("l1", "landlord is not returning my deposit of 40000", language_override="hi")
    assert any("ऀ" <= ch <= "ॿ" for ch in out)


def test_abstain_clears_previous_answer(db):
    p = NyayaMitraPipeline(db, factory(), today=date(2026, 11, 9))
    st, _ = run(p, "a1", DEPOSIT_FLOW)
    assert st.answer_en_md
    p2 = NyayaMitraPipeline(db, factory({"always_fabricate": True, "no_options": True}), today=date(2026, 11, 9))
    st, _ = run(p2, "a1", ["what if he refuses?"])
    assert st.status != "ABSTAINED" or st.answer_en_md is None


def test_retrieval_cap_is_hard(db):
    p = NyayaMitraPipeline(db, factory(), today=date(2026, 11, 9))
    st, _ = run(p, "s6", DEPOSIT_FLOW + [
                          "what if he still refuses?", "can I also complain to police?", "and one more thing?"])
    assert st.retrieval_calls == MAX_RETRIEVAL_CALLS
    assert any(x.get("blocked") for x in st.retrieval_log) or len(st.retrieval_log) == MAX_RETRIEVAL_CALLS


# ------------------------------------------------------------ checklist redesign
def test_guessed_critical_fact_is_rejected(db):
    """'my boss is not giving me money' must not tick 'Employment status' with a hedged guess."""
    p = NyayaMitraPipeline(db, factory(), today=date(2026, 11, 9))
    st, out = p.handle("g1", "my boss is not giving me money")
    assert st.checklist["l_status"]["status"] == "MISSING"
    assert st.pending_field == "l_status"


def test_fields_follow_problem_type(db):
    p = NyayaMitraPipeline(db, factory(), today=date(2026, 11, 9))
    st, _ = p.handle("pt1", "landlord is not returning my deposit of 40000")
    assert st.sub_issues.get("Property Law") == ["deposit"]
    assert "p_deposit_amount" in st.checklist and "p_vacated" in st.checklist
    assert "p_notice" not in st.checklist and "p_possession_due" not in st.checklist  # eviction / builder fields


def test_contextual_question_used_only_for_the_right_topic(db):
    good = {"field_id": "p_location", "text": "You mentioned the deposit — which city and state is the flat in?"}
    st, out = NyayaMitraPipeline(db, factory({"question": good}), today=date(2026, 11, 9)).handle("cq1", DEPOSIT_FLOW[0])
    assert out == good["text"]
    wrong = {"field_id": "p_vacated", "text": "When did you vacate?"}  # engine wants p_location first
    st, out = NyayaMitraPipeline(db, factory({"question": wrong}), today=date(2026, 11, 9)).handle("cq2", DEPOSIT_FLOW[0])
    assert "city and state" in out


def test_closing_question_asks_for_domain_proof(db):
    p = NyayaMitraPipeline(db, factory(), today=date(2026, 11, 9))
    st, out = run(p, "cl1", DEPOSIT_FLOW[:3])
    assert st.status == "AWAITING_ADDITIONAL" and "rent or sale agreement" in out[-1]


def test_hedge_filter():
    from checklists.engine import is_real_value
    assert not is_real_value("Employed or formerly employed, given there is a boss")
    assert not is_real_value("Money owed, probably salary")
    assert is_real_value("Followed by an unknown man near the market")
    assert is_real_value("₹40,000 deposit")


def test_one_fact_per_question(db):
    """Each turn asks about exactly one missing critical field."""
    from checklists.engine import next_missing_group
    p = NyayaMitraPipeline(db, factory(), today=date(2026, 11, 9))
    st, out = p.handle("one1", "my boss is not giving me money")
    g = next_missing_group(st.checklist)
    assert g["field_ids"] == [st.pending_field] == ["l_status"]
    assert out.count("?") == 1  # fixed fallback question is a single question


# ------------------------------------------------------------ follow-up with a new problem / simulated users
def test_followup_new_problem_asks_questions_then_answers_with_its_law(db):
    p = NyayaMitraPipeline(db, factory(), today=date(2026, 11, 9))
    st, _ = run(p, "fu1", DEPOSIT_FLOW)
    assert st.status == "COMPLETED" and "Criminal Law" not in st.domains
    st, out = p.handle("fu1", "he also threatened to beat me yesterday when i asked again")
    assert "Criminal Law" in st.domains
    assert st.status == "CLARIFYING" and st.pending_field.startswith("r_")  # asks before answering
    for _ in range(6):
        if st.status != "CLARIFYING":
            break
        st, out = p.handle("fu1", "my landlord threatened to beat me in pune on 8 november, no police complaint yet")
    assert st.status == "COMPLETED"
    kb = get_kb()
    assert any("Criminal Law" in kb.get(i).domains for i in st.evidence_ids)  # law for the new area was retrieved
    assert st.retrieval_calls <= MAX_RETRIEVAL_CALLS


def test_followup_same_problem_answers_directly(db):
    p = NyayaMitraPipeline(db, factory(), today=date(2026, 11, 9))
    run(p, "fu2", DEPOSIT_FLOW)
    st, out = p.handle("fu2", "what if he still refuses to pay me back?")
    assert st.status == "COMPLETED" and "Sources" in out


def test_simulated_user_finishes_conversation(db):
    from scripts.run_cases import converse
    p = NyayaMitraPipeline(db, factory(), today=date(2026, 11, 9))
    case = {"answers": {"p_location": "Pune", "p_vacated": "i vacated in august"}, "closing": "no"}
    st, _ = p.handle("sim1", DEPOSIT_FLOW[0])
    md = []
    st = converse(p, "sim1", case, md, st)
    assert st.status == "COMPLETED" and any("Sources" in line for line in md)


def test_cases_file_is_valid():
    import json as _json
    import os as _os
    from checklists.definitions import DOMAIN_CHECKLISTS
    ids = {f.field_id for fs in DOMAIN_CHECKLISTS.values() for f in fs}
    cases = _json.load(open(_os.path.join(_os.path.dirname(__file__), "cases.json"), encoding="utf-8"))
    for c in cases:
        assert c["turns"], c["id"]
        unknown = set(c.get("answers", {})) - ids
        assert not unknown, f"{c['id']}: unknown field ids {unknown}"


# ------------------------------------------------------------ re-asking an incomplete field
def test_mislabelled_decline_is_asked_again_with_acknowledgement(db):
    """'he is chasing me' to a date question: even if LLM 1 says DECLINED, the user never said
    "I don't know", so the fact is saved and the question is asked again (not marked 'not provided')."""
    p = NyayaMitraPipeline(db, factory({"force_status": "DECLINED"}), today=date(2026, 11, 9))
    st, _ = p.handle("rd1", DEPOSIT_FLOW[0])
    asked = st.pending_field
    st, out = p.handle("rd1", "he is chasing me right now near my house")
    assert st.pending_field == asked and st.checklist[asked]["status"] == "MISSING"
    assert out.startswith("Thank you for telling me")  # acknowledges, does not say "sorry"
    assert "he is chasing me right now near my house" in st.case_statements_en


def test_explicit_dont_know_is_not_asked_again(db):
    p = NyayaMitraPipeline(db, factory(), today=date(2026, 11, 9))
    st, _ = p.handle("rd2", DEPOSIT_FLOW[0])
    asked = st.pending_field
    st, out = p.handle("rd2", "i don't know")
    assert st.checklist[asked]["status"] == "UNRESOLVED" and st.pending_field != asked


def test_explicit_decline_regex():
    from orchestrator.pipeline import EXPLICIT_DECLINE
    for s in ["I don't remember", "not sure", "mujhe pata nahi", "याद नहीं", "I’d prefer not to say".replace("’", "'"), "skip"]:
        assert EXPLICIT_DECLINE.search(s), s
    for s in ["he is chasing me", "my landlord threatened me", "in Pune"]:
        assert not EXPLICIT_DECLINE.search(s), s


# ------------------------------------------------------------ general / hypothetical questions
def test_general_question_answered_without_intake(db):
    p = NyayaMitraPipeline(db, factory(), today=date(2026, 11, 9))
    st, out = p.handle("gq1", "can i defend myself against a thief that may come?")
    assert st.mode == "general" and st.status == "COMPLETED"
    assert st.questions_asked == 0 and not st.checklist          # no "on what date did this happen?"
    assert "What the law says" in out and "Sources" in out
    assert "BNS2023_S34_35" in st.evidence_ids                   # private-defence law retrieved


def test_general_followup_stays_general(db):
    p = NyayaMitraPipeline(db, factory(), today=date(2026, 11, 9))
    p.handle("gq2", "can i defend myself against a thief that may come?")
    st, out = p.handle("gq2", "can i use a stick?")
    assert st.mode == "general" and st.status == "COMPLETED" and st.questions_asked == 0
    assert len(st.case_statements_en) == 2                       # previous question kept as context


def test_real_incident_after_general_question_opens_a_case(db):
    p = NyayaMitraPipeline(db, factory(), today=date(2026, 11, 9))
    p.handle("gq3", "can i defend myself against a thief that may come?")
    st, out = p.handle("gq3", "a thief broke into my house last night")
    assert st.mode == "case" and st.checklist and "Criminal Law" in st.domains
    assert st.status in ("CLARIFYING", "AWAITING_ADDITIONAL")    # intake questions start


def test_private_defence_retrieval():
    ids = [d.doc_id for d in get_kb().search(["can I defend myself against a thief at night"], ["Criminal Law"])]
    assert ids[0] == "BNS2023_S34_35" and "BNS2023_S41" in ids and "BNS2023_S37" in ids
