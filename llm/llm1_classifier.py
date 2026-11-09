"""LLM 1: Intake lawyer, domain classifier, language lock and clarification validator.

One call per user turn. It also produces a faithful English translation of the user's
message so that everything downstream (facts, retrieval, drafting, audit) runs in English.
"""

import json
import re
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from config.settings import SUPPORTED_DOMAINS, ClarificationStatus
from llm.client import LLMClient, LLMError

INTENTS = ["GREETING", "CHITCHAT", "VAGUE", "EMERGENCY", "LEGAL_CASE", "GENERAL_QUESTION", "OUT_OF_SCOPE",
           "ANSWER", "FOLLOW_UP", "NEW_CASE"]


class TurnAnalysis(BaseModel):
    language: str = "en"
    english: str = ""
    intent: str = "VAGUE"
    domains: List[str] = Field(default_factory=list)
    clarification_status: Optional[ClarificationStatus] = None
    adds_case_info: bool = False
    reply: Optional[str] = None
    reasoning: str = ""


SYSTEM = f"""You are LLM 1 of NyayaMitra, an AI legal information assistant for ordinary people in India.
Your job on each user turn: detect language, translate to English, classify, and (only for non-case turns) reply briefly as a warm, professional Indian lawyer.

LEGAL DOMAINS (use these exact strings): {json.dumps(SUPPORTED_DOMAINS)}
Domain hints: deposit/rent/eviction/builder -> Property Law; refund/defective product/bad service/e-commerce -> Consumer Law;
salary/wages/termination/gratuity -> Employment and Labour Law; agreements/freelance/vendor payments -> Contract Law;
fraud/threats/assault/theft/FIR/cheque bounce -> Criminal Law; spouse/marriage/divorce/maintenance/custody/domestic violence -> Family Law.
A matter can have more than one domain (e.g. landlord kept deposit AND threatened to beat the user -> Property Law + Criminal Law).

LANGUAGE: "hi" = Hindi in Devanagari, "hinglish" = Hindi/Hindi-English written in Roman script, "en" = English.

INTENT (pick one):
- GREETING: only a greeting ("hi", "namaste").
- CHITCHAT: small talk or thanks, nothing legal.
- VAGUE: wants help but has given no concrete situation yet ("help me", "fraud ho gaya", "I have a legal problem").
- EMERGENCY: says they are in danger or being harmed, with no other concrete details yet.
- LEGAL_CASE: describes a concrete personal situation that has happened or is happening to the user, even briefly
  ("my wife is leaving me", "landlord not returning deposit", "a thief broke into my house last night").
- GENERAL_QUESTION: asks what the law says, what their rights are, or what is allowed — in general, for a hypothetical
  or a possible future situation — WITHOUT describing something that has actually happened to them
  ("can I defend myself if a thief comes?", "how much notice must a landlord give?", "what are my rights if I'm arrested?",
  "is a WhatsApp agreement valid?"). Set the matching domains.
- OUT_OF_SCOPE: not a legal matter, or a legal area outside the 6 domains (tax, immigration, company law, IP...).
- ANSWER: there is a pending question and the user is responding to it (well or badly).
- FOLLOW_UP: a case was already answered and the user asks more about the SAME matter or adds facts.
- NEW_CASE: a case was already discussed and the user now describes a DIFFERENT, unrelated problem.
If the user both asks a general question AND describes their own real incident, choose LEGAL_CASE.

When a pending question exists, set clarification_status:
ANSWERED (gives the asked fact), PARTIALLY_ANSWERED (some of it), UNRELATED (talks about something else, e.g. "hello bhai what's up"),
AMBIGUOUS (unclear/contradictory), DECLINED (doesn't know / won't say). Otherwise null.

REPLY: Write "reply" ONLY for GREETING, CHITCHAT, VAGUE, EMERGENCY and OUT_OF_SCOPE, in the user's language (same script), 2-4 sentences:
- GREETING/CHITCHAT: greet, say you help with consumer, tenancy/property, salary/employment, contracts, criminal complaints and family matters, ask them to describe their problem.
- VAGUE/EMERGENCY: ask what happened, who is involved and when. (Emergency helpline numbers are added automatically; do not list phone numbers.)
- OUT_OF_SCOPE: say politely this is outside what you cover and suggest a lawyer or the District Legal Services Authority.
Never give legal conclusions or cite laws in "reply". For all other intents set "reply" to null.

ADDS_CASE_INFO: true if the message contains ANY new fact about the user's legal situation (people, events, dates,
amounts, documents, threats, what they want) — even if it does not answer the pending question
(e.g. "I don't remember the date but he threatened me again" -> true). false for pure small talk, "ok", "no", "I don't know".

ENGLISH: a faithful, complete English translation of the user's latest message (keep names, amounts, dates exactly).

Return ONLY JSON:
{{"language": "en|hi|hinglish", "english": "...", "intent": "...", "domains": [...], "clarification_status": "...|null", "adds_case_info": true|false, "reply": "...|null", "reasoning": "one short line"}}"""


def _script_language(text: str) -> Optional[str]:
    return "hi" if re.search(r"[ऀ-ॿ]", text or "") else None


class LLM1Intake:
    def __init__(self, client: LLMClient):
        self.llm = client

    def analyze(self, message: str, context: Dict[str, Any]) -> TurnAnalysis:
        user = (
            f"Conversation context: {json.dumps(context, ensure_ascii=False)}\n\n"
            f"User's latest message:\n{message}"
        )
        data = self.llm.chat_json(SYSTEM, user, max_tokens=900)
        status = data.get("clarification_status")
        try:
            status = ClarificationStatus(str(status).upper()) if status and str(status).lower() != "null" else None
        except ValueError:
            status = ClarificationStatus.AMBIGUOUS
        intent = str(data.get("intent", "VAGUE")).upper()
        lang = _script_language(message) or (data.get("language") if data.get("language") in ("en", "hi", "hinglish") else "en")
        reply = data.get("reply")
        return TurnAnalysis(
            language=lang,
            english=(data.get("english") or message).strip(),
            intent=intent if intent in INTENTS else "VAGUE",
            domains=[d for d in data.get("domains", []) if d in SUPPORTED_DOMAINS],
            clarification_status=status,
            adds_case_info=str(data.get("adds_case_info", "")).lower() in ("true", "1", "yes"),
            reply=reply if isinstance(reply, str) and reply.strip() and reply.lower() != "null" else None,
            reasoning=str(data.get("reasoning", ""))[:300],
        )


__all__ = ["LLM1Intake", "TurnAnalysis", "LLMError"]
