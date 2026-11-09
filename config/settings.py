"""NyayaMitra configuration. Everything tunable lives in .env.

Model swap: each LLM role is configured as "provider:model", e.g.
    LLM1_MODEL=groq:qwen/qwen3.8-27b
    LLM2_MODEL=gemini:gemini-3.5-flash-lite
Any OpenAI-compatible endpoint works (see PROVIDERS in llm/client.py).
"""

import os
from enum import Enum
from typing import List

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"))

# ---- Hard limits (enforced in Python, not by the model) ----
MAX_RETRIEVAL_CALLS: int = int(os.getenv("MAX_RETRIEVAL_CALLS", "2"))
MAX_GROUNDING_RETRIES: int = int(os.getenv("MAX_GROUNDING_RETRIES", "1"))
MAX_CLARIFICATION_RETRIES: int = int(os.getenv("MAX_CLARIFICATION_RETRIES", "1"))
MAX_TOTAL_CLARIFICATIONS: int = int(os.getenv("MAX_TOTAL_CLARIFICATIONS", "4"))

# ---- API keys ----
API_KEYS = {
    "sarvam": os.getenv("SARVAM_API_KEY", ""),
    "gemini": os.getenv("GEMINI_API_KEY", ""),
    "groq": os.getenv("GROQ_API_KEY", ""),
    "openai": os.getenv("OPENAI_API_KEY", ""),
}

_G = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
_Q = os.getenv("GROQ_MODEL", "qwen/qwen3.8-27b")
_S = os.getenv("SARVAM_MODEL", "sarvam-105b")

# ---- Per-role models ("provider:model"). The auditor deliberately uses a different
# provider from the drafter so they do not share blind spots. ----
ROLE_MODELS = {
    "llm1": os.getenv("LLM1_MODEL", f"groq:{_Q}"),          # intake, classifier, validator
    "llm2": os.getenv("LLM2_MODEL", f"gemini:{_G}"),        # facts, queries, drafting
    "llm3": os.getenv("LLM3_MODEL", f"groq:{_Q}"),          # independent auditor
    # English -> Hindi / Hinglish. (sarvam-105b is a reasoning model: it spent its whole token budget
    # thinking and returned empty translations in testing, so it is only a fallback here; Sarvam is used for voice.)
    "translate": os.getenv("TRANSLATE_MODEL", f"gemini:{_G}"),
}
# Tried in order if a role's provider fails (rate limit, outage).
FALLBACK_MODELS: List[str] = [
    m.strip() for m in os.getenv("FALLBACK_MODELS", f"gemini:{_G},groq:{_Q},sarvam:{_S}").split(",") if m.strip()
]
# Set LLM_PROVIDER=mock to run fully offline with the scripted test LLM.
LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "auto").lower()

DATABASE_PATH: str = os.getenv(
    "DATABASE_PATH",
    os.path.join(os.path.dirname(os.path.dirname(__file__)), "nyayamitra.db"),
)


class LegalDomain(str, Enum):
    CONSUMER = "Consumer Law"
    PROPERTY = "Property Law"
    LABOUR = "Employment and Labour Law"
    CONTRACT = "Contract Law"
    CRIMINAL = "Criminal Law"
    FAMILY = "Family Law"


SUPPORTED_DOMAINS: List[str] = [d.value for d in LegalDomain]
HIGH_RISK_DOMAINS = {LegalDomain.CRIMINAL.value, LegalDomain.FAMILY.value}


class ClarificationStatus(str, Enum):
    ANSWERED = "ANSWERED"
    PARTIALLY_ANSWERED = "PARTIALLY_ANSWERED"
    UNRELATED = "UNRELATED"
    AMBIGUOUS = "AMBIGUOUS"
    DECLINED = "DECLINED"


class GroundingStatus(str, Enum):
    PASS = "PASS"
    REVISE = "REVISE"
    RETRIEVE_AGAIN = "RETRIEVE_AGAIN"
    ABSTAIN = "ABSTAIN"


LANGUAGES = {"en": "English", "hi": "Hindi", "hinglish": "Hinglish"}
