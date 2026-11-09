"""Config sanity: limits load and every role has a provider:model."""

from config.settings import MAX_GROUNDING_RETRIES, MAX_RETRIEVAL_CALLS, ROLE_MODELS
from llm.client import PROVIDERS


def test_limits():
    assert MAX_RETRIEVAL_CALLS >= 1 and MAX_GROUNDING_RETRIES >= 0


def test_roles_configured():
    for role in ("llm1", "llm2", "llm3", "translate"):
        provider, model = ROLE_MODELS[role].split(":", 1)
        assert provider in PROVIDERS and model
