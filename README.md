# NyayaMitra (न्यायमित्र) — legal help in your language

A conversational AI that helps ordinary people in India understand an everyday legal problem
and act on it. The person types or speaks in English, Hindi or Hinglish. NyayaMitra asks only
the questions it still needs, one at a time, then answers like a lawyer would:

- where they stand legally
- the options open to them
- the time limits that apply
- what to do next
- what evidence to keep
- a draft notice or complaint
- when to involve a real lawyer

Every legal statement cites a Bare Act provision and is audited before the person sees it.
If the audit cannot verify a point, that point is removed. If nothing reliable remains,
NyayaMitra refers the person to a lawyer or free legal aid instead of guessing.

---

## Run it

```bash
cd "AI lawyer Claude"
pip install -r requirements.txt
cp .env.example .env            # add GROQ_API_KEY and GEMINI_API_KEY (free tiers); SARVAM_API_KEY for voice
streamlit run app.py            # run from this folder so the light theme in .streamlit/ is picked up
```

`.env` is read only when the app starts. Restart Streamlit after changing it.

**Tests and raw outputs**

```bash
python3 -m pytest -q tests          # 47 offline tests, scripted fake LLM, no API calls
python3 scripts/run_cases.py        # live: runs the 11 simulated users in tests/cases.json -> outputs/
python3 scripts/run_cases.py 02 05  # only some cases
```

---

## Architecture (three LLMs, rules in code)

```
user message (text, or voice -> Sarvam speech-to-text)
  │
  ├─ Safety rules (Python, before any model)
  │    danger / domestic violence / self-harm / cyber-fraud keywords in English, Hindi, Hinglish
  │    -> helplines 112 / 181 / 14416 / 1930 shown immediately
  │
  ├─ LLM 1  Intake lawyer + classifier + validator (one call per turn)
  │    · language (en / hi / hinglish, locked once a case starts) and a faithful English translation
  │    · intent and legal domains
  │    · was the pending question answered? ANSWERED / PARTIAL / UNRELATED / AMBIGUOUS / DECLINED
  │    · does the message contain new case facts even if it doesn't answer the question?
  │    greetings, vague messages, emergencies and out-of-scope questions are answered by LLM 1 directly
  │    GENERAL_QUESTION ("can I defend myself if a thief comes?") skips the intake: retrieval -> draft -> audit
  │
  ├─ LLM 2  Intake form (one call): problem type -> facts -> next question
  │    · detects the type of problem (e.g. Property: deposit / eviction / lock-out / builder delay)
  │    · fills checklist fields with SPECIFIC facts only; guessed or hedged values are rejected in code
  │    · phrases the next question in context, in the user's language
  │
  ├─ Checklist engine (Python)
  │    · only fields that apply to the detected problem type
  │    · ONE critical fact asked per turn, in priority order (safety first)
  │    · repeats an unanswered question (MAX_CLARIFICATION_RETRIES), then marks it "not provided"
  │    · at most MAX_TOTAL_CLARIFICATIONS questions, then a closing question that asks for proof
  │
  ├─ Retrieval tool (Python, hard cap MAX_RETRIEVAL_CALLS per consultation)
  │    LLM 2 writes English queries -> BM25 over kb/provisions.json (74 provisions)
  │    filtered by domain and by criminal-law date (IPC/CrPC before 1 July 2024, BNS/BNSS after)
  │    + linked companion provisions (limitation, forum, fees)
  │
  ├─ Rules engine (Python): time elapsed, consumer forum by amount, IPC vs BNS, limitation warnings
  │
  ├─ LLM 2  Draft (English, JSON): every legal point = {text, cites: [doc_id]}
  │
  ├─ LLM 3  Auditor (a different provider from the drafter)
  │    Layer 1 (deterministic, verification/checks.py)
  │      · every cited doc_id was actually retrieved
  │      · every section / Article / Rule mentioned is in the evidence
  │      · every Act named is in the evidence (no IPC when BNS applies, no Consumer Protection Act 1986)
  │      · every amount / period / % appears in the cited provision, the user's facts or computed facts
  │    Layer 2 (semantic): each statement is checked against the provision it cites
  │    -> PASS | REVISE | RETRIEVE_AGAIN | ABSTAIN        (if the audit cannot run, it fails closed)
  │
  ├─ Bounded correction (MAX_GROUNDING_RETRIES = 1)
  │    one redraft with the exact issues as feedback (plus one extra search if law was missing)
  │    still failing -> take the better attempt, remove only the failing points, re-check, deliver
  │    with a note if real content remains; otherwise refuse and refer to a lawyer / NALSA 15100
  │
  └─ Deterministic rendering + translation
       citations, the lawyer-referral block and the disclaimer are written by code, not the model
       translated to Hindi / Hinglish after the audit; if any number or citation is lost, English is shown
```

Everything internal runs in English. Only the questions and the final answer are in the user's language.
The audited English original is always visible in the inspector's "Audit" tab.

---

## How a conversation works

**1. Only what's still needed is asked.** From *"meri wife mujhe chhod ke ja rahi hai"* the system already
knows the relationship (husband and wife), so it never asks about it. It asks what has happened, then what you want.

**2. No guessing.** From *"my boss is not giving me money"* it does **not** record "employed" or "salary
unpaid". Those aren't stated, so it asks. Values like "probably…" or "given there is a boss…" are rejected in
code even if the model writes them.

**3. Checklists depend on the type of problem.** A field is critical only if its answer changes the forum,
the time limit, which law applies, eligibility for a remedy, or safety:

| Domain | Problem types | Examples of critical facts |
|---|---|---|
| Consumer | defective product, poor service, online order | amount (decides the forum), date (2-year limit), already complained? |
| Property | deposit, eviction, lock-out, builder delay | deposit amount, date vacated; lock-out date (6-month limit); promised possession date |
| Labour | unpaid salary, terminated, gratuity | employer type, months and amount unpaid, years of service (1 year / 5 years) |
| Contract | unpaid work, non-performance, cheque bounce | amount, date (3-year limit), arbitration clause, cheque return date |
| Criminal | fraud, online fraud, threat, assault, theft, stalking… | **safe right now?**, date (IPC vs BNS), money lost and how paid, police status |
| Family | spouse left, divorce, maintenance, violence, custody… | **safe right now?** (abuse), marriage law, marriage date and time apart, case already filed? |

Full list: [checklists/definitions.py](checklists/definitions.py).

**4. One question per turn.** Each turn asks about exactly one missing fact, phrased around what the person
said (*"Since you are still working there, what kind of employer is it…?"*). If LLM 2's phrasing targets the
wrong field or is in the wrong script, a fixed question is used instead (47 fixed questions in 3 languages).

**5. Useful facts are kept even when they don't answer the question.** *"I don't remember the date, but he
threatened me again"* marks the date "not provided", saves the threat, and adds Criminal Law.

**6. An unanswered question is asked again.** If a reply doesn't answer the question, the question is
repeated (up to `MAX_CLARIFICATION_RETRIES`), then the system moves on:
- If the reply shared something about the case (*"he is chasing me…"*), the system acknowledges it first:
  *"Thank you for telling me — I've noted that…"*.
- If it didn't (*"hello bhai what's up"*), the question is simply asked again.
- A field is marked "not provided" straight away only when the person actually says they don't know or won't
  say (*"I don't remember"*, *"pata nahi"*). This is checked in code, not just on the model's label.

**7. A follow-up that raises a new problem gets its own questions.** After an answer, *"he also threatened to
beat me"* adds Criminal Law and asks its critical questions first, with one retrieval call of its own. Then
both problems are answered together. A follow-up about the same problem is answered directly.

**8. General questions are answered directly.** *"Can I defend myself if a thief comes?"* or *"How much notice
must a landlord give?"* is a question about the law, not the person's own incident, so there are no intake
questions. It retrieves the law, drafts and audits as usual, and answers under "What the law says". If the person
then describes something that actually happened, a normal case starts with its questions.

**9. Closing question asks for proof.** For example, salary slips and bank statements for a wage claim, or the
rent agreement and deposit receipt for a deposit dispute.

---

## Why the model cannot invent law here

1. It only sees retrieved provisions and must cite their `doc_id`s. Case law is never cited.
2. Python rejects any unknown `doc_id`, section number, Act name or number before a second model checks
   the meaning.
3. The citation list, the lawyer-referral rules and the disclaimer are rendered by code.
4. When verification fails, the failing points are removed or the system refuses. Unverified statements
   are never shown.

**What this does not guarantee:**
- **The Layer-2 auditor is a model and can miss an error.** Layer 1 is exact, but only for citations,
  sections, Act names and numbers.
- **Some parts aren't checked for meaning.** The draft notice and the "Assumptions" list get only the Layer-1
  checks, and "Keep these ready" is not audited.
- **Answers are checked against the knowledge-base summaries, not the official text.** A wrong summary would
  be confirmed.
- **Translation happens after the audit.** Numbers and citations are checked to survive it; subtle changes in
  meaning are not.

---

## Model swap

Each role is one line in `.env`:

```
LLM1_MODEL=groq:qwen/qwen3.8-27b          # intake, classifier, validator
LLM2_MODEL=gemini:gemini-3.5-flash-lite   # facts, questions, queries, drafting
LLM3_MODEL=groq:qwen/qwen3.8-27b          # auditor (keep a different provider from LLM2)
TRANSLATE_MODEL=gemini:gemini-3.5-flash-lite
```

Any OpenAI-compatible endpoint can be added in `llm/client.py → PROVIDERS`. If a provider fails (rate limit,
outage), the next one in `FALLBACK_MODELS` is tried automatically, and the inspector's Usage tab shows which
model answered. There is no silent fake output.

When Groq is rate-limited, the auditor falls back to Gemini, so for that turn the drafter and auditor share a
provider. This happened in case 06 below.

`sarvam-105b` was tried as the translator. It is a reasoning model, spent its whole token budget thinking, and
returned empty translations, so it is now only a fallback. Sarvam is used for voice input.

---

## Results on the test cases (`outputs/`)

The 11 cases in `tests/cases.json` are **simulated users**. Each one knows its facts and answers whatever is
asked, so the scripts don't break when the questions change. Raw transcripts and full state are in `outputs/`.

| # | Case | Questions | Outcome | Audit |
|---|---|---|---|---|
| 01 | Deposit not returned (English) | 1 | Model Tenancy Act s.11 with its state-adoption caveat; legal notice | REVISE, then PASS |
| 02 | Wife has left (Hinglish) | 5 | relationship never asked; restitution of conjugal rights, HMA s.9 | PASS |
| 03 | Defective TV from Amazon | 0 | District Commission by amount; e-commerce grievance officer | RETRIEVE_AGAIN, then PASS |
| 04 | Fired, salary unpaid (Hindi) | 2 | Code on Wages s.17 / s.45, IR Code s.70; draft wage claim in Hindi | PASS |
| 05 | Landlord lock-out + threat | 5 | Property + Criminal; Specific Relief Act s.6, BNS s.351; helpline 112 | PASS |
| 06 | Job fraud, March 2024 | 3 | IPC s.420, not BNS (incident before 1 July 2024) | PASS |
| 07 | "I am in danger", then abuse | 5 | helplines 112 and 181 first; domestic violence case opened | PASS |
| 08 | Income tax question | 0 | politely declined as out of scope | — |
| 09 | Fake "Section 420B" | 1 | says it could not find Section 420B; explains the real remedy | PASS |
| 10 | Off-topic replies | 4 | question repeated, then moved on | PASS |
| 11 | Follow-up raises a threat | 3 | Criminal questions asked after the deposit answer; BNS s.351 added | REVISE, then PASS |

All 10 cases that reached an answer passed the audit: 7 on the first draft and 3 after one correction.
None were refused and no points had to be removed.

---

## Cost and scale

Measured over the 10 answered cases in `outputs/`:
- 8–21 model calls per consultation (more questions mean more calls)
- about 21,600 input and 4,200 output tokens on average
- 28–93 seconds of total model time across the whole conversation

Every message carries a fixed cost of about 1,000 tokens for LLM 1's instructions, even "hello".

| | Per consultation | 100,000 consultations / month |
|---|---|---|
| Free tiers (as built) | ₹0 | rate limits apply; not suitable |
| Paid small models, assumed $0.10 / $0.40 per million tokens (input / output) | ≈ $0.004 | ≈ $400 |

**Free parts:** safety, checklist, retrieval, rules, the Layer-1 audit and rendering run in Python, cost
nothing, and take milliseconds.

**To cut cost:**
- answer plain greetings with a rule instead of LLM 1
- prompt caching for the repeated instructions and evidence
- send only the facts collected so far to the extractor instead of the full checklist each turn

**Scaling the knowledge base:** move from 74 summaries to the full Bare Acts plus state rules, chunked by
section, keeping the same `doc_id` citation contract. The verifier doesn't change.

**Humans in the loop:**
- Lawyers review the knowledge base (not each answer).
- Every refusal goes to a legal-aid referral queue.
- A sample of passed answers is reviewed every week.

---

## Configuration (`.env`)

| Setting | Default | What it controls |
|---|---|---|
| `MAX_TOTAL_CLARIFICATIONS` | 4 | questions per consultation (a new problem in a follow-up gets its own budget) |
| `MAX_CLARIFICATION_RETRIES` | 1 | repeats of an unanswered question before it is marked "not provided" |
| `MAX_RETRIEVAL_CALLS` | 2 | law searches per consultation (+1 for a new problem raised in a follow-up) |
| `MAX_GROUNDING_RETRIES` | 1 | redrafts after the auditor rejects an answer |

---

## What it covers, and what it doesn't

| Covered (central law) | Not covered |
|---|---|
| Consumer: defects, deficiency, e-commerce, forum, fees, limitation | Tax, immigration, company / IP law |
| Tenancy and property: deposit, notice, lock-out, RERA builder delay | State rent-control Acts (flagged as a gap) |
| Wages: Code on Wages 2019, the older Payment of Wages Act, gratuity, retrenchment | Muslim / Christian personal law, Special Marriage Act |
| Contracts: breach, damages, limitation, arbitration clause, cheque bounce | Court representation, drafting pleadings |
| Criminal: cheating, breach of trust, intimidation, hurt, theft, trespass, right of private defence (self-defence), FIR (BNS/BNSS or IPC/CrPC by date), online fraud | Bail, trial strategy |
| Family (Hindu Marriage Act): restitution, divorce, mutual consent, maintenance, custody, domestic violence | |

The knowledge base holds plain-language summaries written from the official text on indiacode.nic.in, not
verbatim Act text. The less certain figures were checked against legal-commentary sources (not the official
gazette). Labour-code commencement, retrenchment compensation and the consumer fee table were corrected as a
result. A production version would load the full Bare Acts and the state rules.

## Known gaps

- **Stalking:** the criminal checklist has a "stalking / harassment" type, but the knowledge base has no
  stalking provision (BNS s.78), so those cases get only general provisions or a referral.
- **Safety keywords miss some phrasings:** *"mujhe darr lag raha hai"*, *"koi peecha kar raha hai"*, and *"I
  lost money through UPI"* without the word "fraud" don't trigger the helpline banner.
- **One question per turn means longer intakes** for cases with many critical facts (family cases took 5
  questions).
- **The extractor is strict on purpose,** so it sometimes asks for something that was only implied (e.g. "since
  when" after "September and October salary").
- **Model-written Hindi questions can have small spelling slips.** The fixed fallback questions are clean.

---

## Project layout

```
app.py                     Streamlit UI (light theme in .streamlit/config.toml)
orchestrator/pipeline.py   turn handling, intake flow, limits, retry/prune/abstain, translation
orchestrator/render.py     deterministic Markdown rendering of the final answer
llm/client.py              one client for every provider, per-role models, fallback, usage log
llm/llm1_classifier.py     LLM 1: intake, language, intent, domains, answer validation
llm/llm2_agent.py          LLM 2: problem type, facts, next question, queries, draft, translation
llm/llm3_verifier.py       LLM 3: semantic audit + verdict
verification/checks.py     Layer-1 deterministic checks (citations, sections, Acts, numbers)
rules/safety.py            emergency keywords, helplines, lawyer-referral rules
rules/legal_rules.py       dates, forum by amount, IPC-vs-BNS, limitation warnings
kb/provisions.json         74 curated Bare Act provisions; kb/retriever.py = BM25 retrieval
checklists/definitions.py  problem types, checklists, 47 fixed questions in 3 languages, closing questions
checklists/engine.py       checklist rules: applicable fields, next question, guess rejection
persistence/db.py          SQLite session store
voice/transcriber.py       Sarvam speech-to-text
tests/                     47 offline tests + fake LLM; cases.json = 11 simulated users
scripts/run_cases.py       runs the simulated users and writes outputs/
```

An earlier prototype used GraphRAG. It was replaced: the graphs had 36 section nodes and many unconnected
nodes, so a flat cited knowledge base with linked provisions was simpler and easier to verify.
