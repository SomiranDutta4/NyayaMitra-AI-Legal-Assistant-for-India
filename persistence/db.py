"""SQLite persistence. The whole consultation state is stored as one JSON document per session."""

import json
import sqlite3
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from config.settings import DATABASE_PATH


class SessionState(BaseModel):
    session_id: str
    status: str = "NEW"          # NEW, INTAKE, CLARIFYING, AWAITING_ADDITIONAL, COMPLETED, ABSTAINED, ERROR
    mode: str = "case"           # "case" = the user's own situation (intake questions); "general" = a question about the law
    language: str = "en"         # en | hi | hinglish
    language_locked: bool = False
    language_override: Optional[str] = None
    domains: List[str] = Field(default_factory=list)
    transcript: List[Dict[str, str]] = Field(default_factory=list)   # {role, display, en}
    case_statements_en: List[str] = Field(default_factory=list)      # user's statements in English
    checklist: Dict[str, Dict[str, Any]] = Field(default_factory=dict)
    sub_issues: Dict[str, List[str]] = Field(default_factory=dict)   # type of problem per domain
    key_date: Optional[str] = None
    amount_inr: Optional[float] = None
    pending_field: Optional[str] = None
    pending_retries: int = 0
    questions_asked: int = 0
    additional_asked: bool = False
    grounding_retries: int = 0
    safety_flags: List[str] = Field(default_factory=list)
    retrieval_calls: int = 0
    retrieval_log: List[Dict[str, Any]] = Field(default_factory=list)
    evidence_ids: List[str] = Field(default_factory=list)
    computed: Dict[str, Any] = Field(default_factory=dict)
    audit_reports: List[Dict[str, Any]] = Field(default_factory=list)
    answer: Optional[Dict[str, Any]] = None           # structured English answer that passed audit
    answer_en_md: Optional[str] = None
    removed_items: List[str] = Field(default_factory=list)
    usage: List[Dict[str, Any]] = Field(default_factory=list)
    last_error: Optional[str] = None


class DatabaseManager:
    def __init__(self, db_path: str = DATABASE_PATH):
        self.db_path = db_path
        with sqlite3.connect(self.db_path) as c:
            c.execute("CREATE TABLE IF NOT EXISTS sessions (session_id TEXT PRIMARY KEY, data TEXT, "
                      "updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")

    def save(self, state: SessionState) -> None:
        with sqlite3.connect(self.db_path) as c:
            c.execute("INSERT OR REPLACE INTO sessions (session_id, data, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP)",
                      (state.session_id, state.model_dump_json()))

    def load(self, session_id: str) -> Optional[SessionState]:
        with sqlite3.connect(self.db_path) as c:
            row = c.execute("SELECT data FROM sessions WHERE session_id = ?", (session_id,)).fetchone()
        return SessionState(**json.loads(row[0])) if row else None
