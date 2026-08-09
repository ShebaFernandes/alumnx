"""Pydantic request/response schemas with exact-match enum validation (§5)."""
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator

from .config import ASSIGNEES, CATEGORIES, PRIORITIES


def _norm_candidate(value: str) -> str:
    """Normalise candidate_id: lowercase, trim, strip +alias (§2)."""
    v = (value or "").strip().lower()
    if "@" in v:
        local, _, domain = v.partition("@")
        local = local.split("+", 1)[0]
        v = f"{local}@{domain}"
    return v


class EnumError(Exception):
    """Raised to produce the exact 400 shape the grader expects."""

    def __init__(self, field: str, received, allowed):
        self.field = field
        self.received = received
        self.allowed = allowed


class TaskCreate(BaseModel):
    candidate_id: str
    source_email_id: str
    thread_id: str
    title: str
    description: Optional[str] = None
    assignee_id: str
    category: str
    priority: str
    due_date: Optional[str] = None
    deal_value_inr: Optional[int] = None
    company_name: Optional[str] = None
    confidence: float = 0.5

    @field_validator("candidate_id")
    @classmethod
    def _clean_candidate(cls, v):
        return _norm_candidate(v)

    @field_validator("assignee_id")
    @classmethod
    def _check_assignee(cls, v):
        if v not in ASSIGNEES:
            raise EnumError("assignee_id", v, ASSIGNEES)
        return v

    @field_validator("category")
    @classmethod
    def _check_category(cls, v):
        if v not in CATEGORIES:
            raise EnumError("category", v, CATEGORIES)
        return v

    @field_validator("priority")
    @classmethod
    def _check_priority(cls, v):
        if v not in PRIORITIES:
            raise EnumError("priority", v, PRIORITIES)
        return v


class TaskPatch(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    assignee_id: Optional[str] = None
    category: Optional[str] = None
    priority: Optional[str] = None
    due_date: Optional[str] = None
    deal_value_inr: Optional[int] = None
    company_name: Optional[str] = None
    confidence: Optional[float] = None

    @field_validator("assignee_id")
    @classmethod
    def _check_assignee(cls, v):
        if v is not None and v not in ASSIGNEES:
            raise EnumError("assignee_id", v, ASSIGNEES)
        return v

    @field_validator("category")
    @classmethod
    def _check_category(cls, v):
        if v is not None and v not in CATEGORIES:
            raise EnumError("category", v, CATEGORIES)
        return v

    @field_validator("priority")
    @classmethod
    def _check_priority(cls, v):
        if v is not None and v not in PRIORITIES:
            raise EnumError("priority", v, PRIORITIES)
        return v


# --- Email + ingest -------------------------------------------------------

class Email(BaseModel):
    email_id: str
    thread_id: str
    message_index: int = 0
    from_name: Optional[str] = None
    from_email: Optional[str] = None
    to: Optional[str] = None
    cc: Optional[List[str]] = None
    subject: Optional[str] = ""
    body: Optional[str] = ""
    received_at: Optional[str] = None
    attachments: Optional[List[str]] = None
    is_reply: Optional[bool] = False

    model_config = {"extra": "allow"}


class IngestRequest(BaseModel):
    candidate_id: str
    emails: List[Email]
    run_id: Optional[str] = None

    @field_validator("candidate_id")
    @classmethod
    def _clean(cls, v):
        return _norm_candidate(v)


class ChatRequest(BaseModel):
    candidate_id: str
    query: str

    @field_validator("candidate_id")
    @classmethod
    def _clean(cls, v):
        return _norm_candidate(v)
