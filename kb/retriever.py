"""Legal retrieval tool over the curated Bare Act knowledge base (kb/provisions.json).

- BM25 keyword ranking over title + summary + lay keywords (queries are always English).
- Domain filter, so a tenancy case never retrieves criminal sections by accident.
- Criminal-law era filter: IPC/CrPC for incidents before 1 July 2024, BNS/BNSS after.
- One-hop expansion through 'related' links (e.g. complaint section -> limitation section).
- The hard cap on calls per consultation is enforced in the pipeline, not trusted to the model.
"""

import json
import math
import os
import re
from collections import Counter
from datetime import date
from typing import Dict, List, Optional

from pydantic import BaseModel, Field

KB_PATH = os.path.join(os.path.dirname(__file__), "provisions.json")
BNS_START = date(2024, 7, 1)
OLD_CRIMINAL_ACTS = ("Indian Penal Code", "Code of Criminal Procedure")
NEW_CRIMINAL_ACTS = ("Bharatiya Nyaya Sanhita", "Bharatiya Nagarik Suraksha Sanhita")

STOPWORDS = set("""a an the of to in on for and or is are was were be by with from at as that this it its
under act section law legal indian india my me i he she they their his her our has have had not no can
do does did will would should could any all what which who whom when where how about into than then""".split())


class LegalDocument(BaseModel):
    doc_id: str
    domains: List[str] = Field(default_factory=list)
    act: str
    section: str
    title: str
    text: str
    keywords: str = ""
    related: List[str] = Field(default_factory=list)

    @property
    def citation(self) -> str:
        return f"{self.section}, {self.act}"


def tokenize(text: str) -> List[str]:
    return [t for t in re.findall(r"[a-z0-9]+", text.lower()) if t not in STOPWORDS and len(t) > 1]


class LegalKnowledgeBase:
    def __init__(self, path: str = KB_PATH):
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        self.docs: Dict[str, LegalDocument] = {
            d["doc_id"]: LegalDocument(**d) for d in data["provisions"]
        }
        # BM25 index
        self._tf = {}
        self._len = {}
        df = Counter()
        for doc_id, d in self.docs.items():
            toks = tokenize(f"{d.title} {d.title} {d.keywords} {d.keywords} {d.text} {d.act}")
            self._tf[doc_id] = Counter(toks)
            self._len[doc_id] = len(toks)
            df.update(set(toks))
        n = len(self.docs)
        self._avg = sum(self._len.values()) / max(n, 1)
        self._idf = {t: math.log(1 + (n - c + 0.5) / (c + 0.5)) for t, c in df.items()}

    def get(self, doc_id: str) -> Optional[LegalDocument]:
        return self.docs.get(doc_id)

    def _bm25(self, doc_id: str, q: List[str], k1: float = 1.4, b: float = 0.75) -> float:
        tf, dl = self._tf[doc_id], self._len[doc_id]
        s = 0.0
        for t in q:
            if t in tf:
                f = tf[t]
                s += self._idf[t] * f * (k1 + 1) / (f + k1 * (1 - b + b * dl / self._avg))
        return s

    @staticmethod
    def _era_ok(doc: LegalDocument, incident_date: Optional[date]) -> bool:
        if incident_date is None:
            return True
        if incident_date < BNS_START:
            return not doc.act.startswith(NEW_CRIMINAL_ACTS) or "Repeal" in doc.title
        return not doc.act.startswith(OLD_CRIMINAL_ACTS)

    def search(
        self,
        queries: List[str],
        domains: List[str],
        top_k: int = 5,
        max_total: int = 9,
        criminal_incident_date: Optional[date] = None,
        exclude: Optional[List[str]] = None,
    ) -> List[LegalDocument]:
        exclude = set(exclude or [])
        pool = [
            d for d in self.docs.values()
            if (not domains or set(d.domains) & set(domains))
            and self._era_ok(d, criminal_incident_date)
            and d.doc_id not in exclude
        ]
        scores = Counter()
        for q in queries:
            qt = tokenize(q)
            for d in pool:
                scores[d.doc_id] += self._bm25(d.doc_id, qt)
        ordered = [doc_id for doc_id, s in scores.most_common() if s > 0]
        if len(domains) > 1:
            # rank within each domain so one domain cannot crowd the other out
            per = max(4, top_k // len(domains) + 1)
            ranked = []
            for dom in domains:
                ranked += [i for i in ordered if dom in self.docs[i].domains and i not in ranked][:per]
            max_total += 3
        else:
            ranked = ordered[:top_k]

        # one-hop expansion through 'related' links
        out = list(ranked)
        for doc_id in ranked:
            for rel in self.docs[doc_id].related:
                rd = self.docs.get(rel)
                if (rd and rel not in out and rel not in exclude and len(out) < max_total
                        and self._era_ok(rd, criminal_incident_date)):
                    out.append(rel)
        return [self.docs[i] for i in out]


_KB: Optional[LegalKnowledgeBase] = None


def get_kb() -> LegalKnowledgeBase:
    global _KB
    if _KB is None:
        _KB = LegalKnowledgeBase()
    return _KB
