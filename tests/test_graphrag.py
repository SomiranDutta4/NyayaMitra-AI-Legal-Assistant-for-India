"""Knowledge-base integrity (the GraphRAG graphs were replaced by kb/provisions.json)."""

from config.settings import SUPPORTED_DOMAINS
from kb.retriever import get_kb


def test_every_domain_has_provisions():
    kb = get_kb()
    for d in SUPPORTED_DOMAINS:
        assert sum(1 for doc in kb.docs.values() if d in doc.domains) >= 5, d


def test_related_links_resolve():
    kb = get_kb()
    for doc in kb.docs.values():
        for r in doc.related:
            assert kb.get(r) is not None, f"{doc.doc_id} -> {r}"
