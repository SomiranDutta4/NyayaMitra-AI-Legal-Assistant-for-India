"""NyayaMitra — Streamlit app. Run:  streamlit run app.py"""

import hashlib

import streamlit as st

from config.settings import (LANGUAGES, MAX_GROUNDING_RETRIES, MAX_RETRIEVAL_CALLS, MAX_TOTAL_CLARIFICATIONS,
                             ROLE_MODELS)
from kb.retriever import get_kb
from orchestrator.pipeline import NyayaMitraPipeline
from voice.transcriber import SarvamVoiceTranscriber

st.set_page_config(page_title="NyayaMitra — Legal help in your language", page_icon=":material/balance:", layout="wide")

st.markdown("""
<style>
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&display=swap');
  html, body, [class*="css"], .stMarkdown, .stButton button, .stTextInput input, textarea, .stSelectbox,
  [data-testid="stChatInput"] textarea {font-family: 'Inter', -apple-system, 'Segoe UI', sans-serif;}

  .block-container {padding-top: 2.4rem; max-width: 1280px;}

  /* header */
  .nm-title {font-size: 1.55rem; font-weight: 600; color: #111827; letter-spacing: -0.01em; margin: 0;}
  .nm-title span {font-weight: 400; color: #6B7280; margin-left: .35rem;}
  .nm-sub {color: #4B5563; font-size: .95rem; line-height: 1.55; margin: .35rem 0 1.4rem 0; max-width: 46rem;}
  .nm-label {font-size: .72rem; font-weight: 600; letter-spacing: .06em; text-transform: uppercase; color: #6B7280;
             margin: 1.1rem 0 .45rem 0;}
  .nm-card {border: 1px solid #E5E7EB; border-radius: 8px; padding: 14px 16px; background: #FAFAFA; margin-bottom: 14px;}
  .nm-card b {font-weight: 600; color: #111827;}
  .nm-steps {margin: .35rem 0 0 0; padding-left: 1.1rem; color: #4B5563; font-size: .9rem; line-height: 1.6;}
  small.muted, .muted {color: #6B7280;}

  /* status chips */
  .nm-pill {display: inline-block; padding: 1px 8px; border-radius: 4px; font-size: .74rem; font-weight: 500;
            margin: 0 6px 6px 0; border: 1px solid #E5E7EB; background: #F9FAFB; color: #374151;}
  .ok {border-color: #BBE5C8; background: #F0FAF3; color: #1E6B34;}
  .warn {border-color: #F1DDA7; background: #FFFBEB; color: #7A5300;}
  .bad {border-color: #F5C2C2; background: #FEF2F2; color: #9B1C1C;}
  .neutral {}

  /* checklist rows */
  .nm-row {padding: 7px 0; border-bottom: 1px solid #F1F2F4;}
  .nm-row .lbl {font-size: .88rem; font-weight: 500; color: #111827;}
  .nm-row .val {font-size: .82rem; color: #6B7280; margin-left: 14px; display: block;}
  .nm-row .tag {font-size: .72rem; color: #1F4E79; margin-left: 6px;}
  .dot {display: inline-block; width: 7px; height: 7px; border-radius: 50%; margin-right: 7px; vertical-align: middle;}
  .dot.COLLECTED {background: #2E7D4F;} .dot.MISSING {border: 1.5px solid #9CA3AF; width: 5px; height: 5px;}
  .dot.UNRESOLVED {background: #D49A1E;}

  /* chat: no avatars; user turns in a quiet box, assistant turns as plain text */
  [data-testid="stChatMessage"] {background: transparent; padding: .25rem 0; gap: 0;}
  [data-testid="stChatMessageAvatarUser"], [data-testid="stChatMessageAvatarAssistant"],
  [data-testid="stChatMessageAvatarCustom"] {display: none;}
  [data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) [data-testid="stChatMessageContent"] {
      background: #F3F4F6; border-radius: 8px; padding: .55rem .85rem; margin-left: auto; max-width: 85%;}
  [data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarAssistant"]) [data-testid="stChatMessageContent"] {
      border-left: 2px solid #1F4E79; padding: .1rem 0 .1rem .9rem;}
  [data-testid="stChatMessage"] h3 {font-size: .98rem; font-weight: 600; color: #111827; margin: 1rem 0 .3rem 0; padding: 0;}
  [data-testid="stChatMessage"] blockquote {background: #FAFAFA; border-left: 2px solid #D1D5DB; padding: .6rem .9rem;
      font-size: .88rem; color: #374151;}
  [data-testid="stChatMessage"] p, [data-testid="stChatMessage"] li {font-size: .94rem; line-height: 1.6; color: #1F2937;}
  [data-testid="stChatMessage"] hr {margin: .9rem 0; border-color: #E5E7EB;}

  /* inputs, buttons, borders */
  [data-testid="stChatInput"] {border: 1px solid #D1D5DB; border-radius: 8px; box-shadow: none;}
  .stButton button {border-radius: 6px; border: 1px solid #E5E7EB; box-shadow: none; font-weight: 500;}
  [data-testid="stSidebar"] [data-testid="stBaseButton-secondary"] {justify-content: flex-start; text-align: left;
      color: #374151; background: #FFFFFF; padding: .4rem .75rem; min-height: 2.1rem;}
  [data-testid="stSidebar"] [data-testid="stBaseButton-secondary"] p {text-align: left; font-size: .85rem;}
  [data-testid="stSidebar"] [data-testid="stBaseButton-secondary"] > div {justify-content: flex-start; width: 100%;}
  [data-testid="stSidebar"] [data-testid="stBaseButton-secondary"]:hover {border-color: #1F4E79; color: #1F4E79;}
  [data-testid="stBaseButton-primary"] {background: #1F4E79; border-color: #1F4E79;}
  [data-testid="stSidebar"] {border-right: 1px solid #E5E7EB; background: #FAFAFA;}
  [data-testid="stExpander"] details {border: 1px solid #E5E7EB; border-radius: 6px;}
  [data-testid="stPopover"] button {font-size: .85rem;}
  .stTabs [data-baseweb="tab"] {font-size: .86rem; font-weight: 500;}
  /* hide only Streamlit's Deploy button and the "Made with Streamlit" line in the menu */
  [data-testid="stAppDeployButton"] {display: none !important;}
  [data-testid="stMainMenuPopover"] [data-testid="stMainMenuList"] ~ div {display: none !important;}
  .nm-brand {font-size: 1.15rem; font-weight: 600; color: #111827; margin: 0;}
  .nm-brand-sub {font-size: .8rem; color: #6B7280; margin: .1rem 0 1rem 0;}
</style>
""", unsafe_allow_html=True)


@st.cache_resource
def get_pipeline():
    return NyayaMitraPipeline()


pipeline = get_pipeline()
ss = st.session_state
ss.setdefault("session_id", pipeline.new_session_id())
ss.setdefault("last_audio", None)
ss.setdefault("queued", None)

EXAMPLES = {
    "Security deposit not returned": "My landlord in Pune is not returning my ₹40,000 security deposit. I vacated the flat on 15 August 2026 and handed over the keys.",
    "Defective TV, refund refused": "I ordered a Sony LED TV from Amazon for ₹45,000 in October 2026. It arrived with a broken screen, and the seller refused a replacement and closed my ticket.",
    "Salary not paid (Hindi)": "मेरी कंपनी ने अक्टूबर 2026 में मुझे बिना नोटिस नौकरी से निकाल दिया और पिछले 2 महीने का ₹80,000 वेतन नहीं दे रही है।",
    "Spouse has left (Hinglish)": "Meri wife mujhe chhod ke apne maayke chali gayi hai aur wapas nahi aana chahti.",
    "Landlord lock-out and threats": "My landlord locked my room, kept my laptop when I asked for my deposit, and threatened to beat me if I go to the police.",
}

# ------------------------------------------------------------------ sidebar
with st.sidebar:
    st.markdown('<p class="nm-brand">NyayaMitra</p><p class="nm-brand-sub">Legal information in your language</p>', unsafe_allow_html=True)
    if st.button("New consultation", width="stretch", type="primary"):
        ss.session_id, ss.last_audio, ss.queued = pipeline.new_session_id(), None, None
        st.rerun()
    lang_choice = st.selectbox("Reply language", ["Auto-detect", "English", "हिंदी (Hindi)", "Hinglish"], index=0)
    override = {"English": "en", "हिंदी (Hindi)": "hi", "Hinglish": "hinglish"}.get(lang_choice)
    show_inspector = st.toggle("Show how it works", value=True)

    st.markdown('<div class="nm-label">Examples</div>', unsafe_allow_html=True)
    for label, text in EXAMPLES.items():
        if st.button(label, width="stretch", key=f"ex_{label}"):
            ss.session_id, ss.queued = pipeline.new_session_id(), text
            st.rerun()

    st.divider()
    st.caption("**Covers:** consumer, tenancy/property, wages & employment, contracts, criminal complaints, family (Hindu Marriage Act).")
    st.caption("**Not covered:** tax, immigration, company/IP law, Muslim/Christian personal law, court representation.")
    with st.expander("Models & limits"):
        for role, name in (("llm1", "LLM 1 · intake"), ("llm2", "LLM 2 · drafting"), ("llm3", "LLM 3 · auditor"), ("translate", "Translator")):
            st.caption(f"**{name}:** `{ROLE_MODELS[role]}`")
        st.caption(f"Retrieval cap {MAX_RETRIEVAL_CALLS} · correction retries {MAX_GROUNDING_RETRIES} · max questions {MAX_TOTAL_CLARIFICATIONS}")
        st.caption(f"Knowledge base: {len(get_kb().docs)} Bare Act provisions")

state = pipeline.load(ss.session_id)

# ------------------------------------------------------------------ layout
if show_inspector:
    col_chat, col_side = st.columns([0.62, 0.38], gap="large")
else:
    col_chat, col_side = st.container(), None

with col_chat:
    st.markdown('<div class="nm-title">NyayaMitra<span>न्यायमित्र</span></div>', unsafe_allow_html=True)
    st.markdown('<p class="nm-sub">Tell me your legal problem in English, हिंदी or Hinglish. I\'ll ask a few questions, '
                'then explain where you stand, your options and next steps — with the exact law cited.</p>',
                unsafe_allow_html=True)

    if not state or not state.transcript:
        st.markdown('<div class="nm-card"><b>How it works</b><ol class="nm-steps">'
                    '<li>Describe what happened, in your own words.</li>'
                    '<li>Answer a few short questions.</li>'
                    '<li>Get your legal position, options, deadlines and a draft notice. Every legal point is '
                    'checked against the Bare Act before you see it.</li></ol></div>', unsafe_allow_html=True)
    else:
        for t in state.transcript:
            with st.chat_message(t["role"]):
                st.markdown(t["display"])

    with st.popover("Voice input"):
        st.caption("Record in Hindi, English or Hinglish (Sarvam speech-to-text).")
        audio = st.audio_input("Record", label_visibility="collapsed")
        if audio is not None:
            b = audio.getvalue()
            h = hashlib.md5(b).hexdigest()
            if h != ss.last_audio:
                ss.last_audio = h
                with st.spinner("Transcribing…"):
                    res = SarvamVoiceTranscriber().transcribe_audio(b)
                if res.get("success") and res.get("transcript"):
                    ss.queued = res["transcript"]
                    st.rerun()
                else:
                    st.warning(res.get("error") or "No speech detected.")

# ------------------------------------------------------------------ inspector
STATUS_LABEL = {"NEW": "New", "INTAKE": "Intake", "CLARIFYING": "Asking questions", "AWAITING_ADDITIONAL": "Final check",
                "PROCESSING": "Working", "COMPLETED": "Answered", "ABSTAINED": "Referred to lawyer", "ERROR": "Service error"}


def pill(text, kind="neutral"):
    return f'<span class="nm-pill {kind}">{text}</span>'


if col_side is not None:
    with col_side:
        st.markdown('<div class="nm-label" style="margin-top:.2rem">Case inspector</div>', unsafe_allow_html=True)
        if not state:
            st.caption("Start a conversation to see the case file, the law retrieved and the audit result.")
        else:
            pills = pill(STATUS_LABEL.get(state.status, state.status), "ok" if state.status == "COMPLETED" else
                         "bad" if state.status in ("ABSTAINED", "ERROR") else "neutral")
            pills += pill(f"Language: {LANGUAGES.get(state.language_override or state.language, state.language)}")
            for d in state.domains:
                pills += pill(d, "warn")
            if state.safety_flags:
                pills += pill("Safety: " + ", ".join(state.safety_flags), "bad")
            st.markdown(pills, unsafe_allow_html=True)
            if state.last_error:
                st.error(f"Model error: {state.last_error[:300]}")

            tab_case, tab_law, tab_audit, tab_usage = st.tabs(["Case", "Law", "Audit", "Usage"])

            with tab_case:
                if not state.checklist:
                    st.caption("No case opened yet.")
                else:
                    rows = []
                    for f in state.checklist.values():
                        tag = '<span class="tag">asking now</span>' if f["field_id"] == state.pending_field else ""
                        cat = ' <span class="muted" style="font-size:.74rem">supporting</span>' if f["category"] != "critical" else ""
                        val = f["value"] or ("not provided" if f["status"] == "UNRESOLVED" else "—")
                        rows.append(f'<div class="nm-row"><span class="dot {f["status"]}"></span><span class="lbl">{f["label"]}</span>'
                                    f'{cat}{tag}<span class="val">{val}</span></div>')
                    st.markdown("".join(rows), unsafe_allow_html=True)
                    st.caption(f"Questions asked: {state.questions_asked}/{MAX_TOTAL_CLARIFICATIONS}")
                    if state.computed:
                        st.markdown("**Computed by rules (not the model)**")
                        st.json({k: v for k, v in state.computed.items() if k != "months_elapsed"}, expanded=False)

            with tab_law:
                st.markdown(pill(f"Retrieval calls {state.retrieval_calls}/{MAX_RETRIEVAL_CALLS}",
                                 "warn" if state.retrieval_calls >= MAX_RETRIEVAL_CALLS else "neutral"), unsafe_allow_html=True)
                for log in state.retrieval_log:
                    if log.get("blocked"):
                        st.caption("A further retrieval was blocked by the hard cap.")
                    else:
                        st.caption(f"Call {log['call']} · queries: " + " | ".join(q[:80] for q in log["queries"]))
                kb = get_kb()
                for i in state.evidence_ids:
                    d = kb.get(i)
                    if d:
                        with st.expander(f"{d.section}, {d.act}"):
                            st.caption(f"`{d.doc_id}` · {d.title}")
                            st.write(d.text)

            with tab_audit:
                if not state.audit_reports:
                    st.caption("The auditor runs once all facts are collected.")
                for rep in state.audit_reports:
                    s = rep["status"]
                    st.markdown(f"**Attempt {rep['attempt']}** " + pill(s, "ok" if s == "PASS" else "warn" if s in ("REVISE", "RETRIEVE_AGAIN") else "bad"),
                                unsafe_allow_html=True)
                    det = rep.get("deterministic_issues") or []
                    st.caption(f"Layer 1 (Python: citations, sections, Acts, numbers): {'passed' if not det else f'{len(det)} issue(s)'}")
                    for d in det:
                        st.caption(f"[{d['item']}] {d['check']}: {d['detail']}")
                    sem = rep.get("semantic_results") or []
                    bad = [x for x in sem if str(x.get("verdict", "")).upper() != "SUPPORTED"]
                    st.caption(f"Layer 2 (independent model): {len(sem) - len(bad)}/{len(sem)} statements supported")
                    for x in bad:
                        st.caption(f"[{x.get('id')}] {x.get('reason', '')}")
                    if rep.get("audit_error"):
                        st.caption(f"Audit error: {rep['audit_error'][:200]}")
                if state.removed_items:
                    st.info(f"Unverifiable points removed before showing the answer: {', '.join(state.removed_items)}")
                if state.answer_en_md and (state.language_override or state.language) != "en":
                    with st.expander("English original (what was audited)"):
                        st.markdown(state.answer_en_md)

            with tab_usage:
                calls = state.usage
                if not calls:
                    st.caption("No model calls yet.")
                else:
                    pt = sum(c.get("prompt_tokens", 0) for c in calls)
                    ct = sum(c.get("completion_tokens", 0) for c in calls)
                    c1, c2, c3 = st.columns(3)
                    c1.metric("Model calls", len(calls))
                    c2.metric("Input tokens", f"{pt:,}")
                    c3.metric("Output tokens", f"{ct:,}")
                    st.dataframe([{"role": c["role"], "model": c["model"], "in": c.get("prompt_tokens", 0),
                                   "out": c.get("completion_tokens", 0), "ms": c.get("ms", 0)} for c in calls],
                                 hide_index=True, width="stretch")

# ------------------------------------------------------------------ input (page level => pinned to the bottom)
typed = st.chat_input("Describe your problem…")
incoming = typed or ss.queued
if incoming:
    ss.queued = None
    with col_chat:
        with st.chat_message("user"):
            st.markdown(incoming)
        with st.chat_message("assistant"):
            with st.status("Understanding your message…", expanded=False) as status_box:
                pipeline.handle(ss.session_id, incoming, language_override=override,
                                progress=lambda label: status_box.update(label=label))
    st.rerun()
