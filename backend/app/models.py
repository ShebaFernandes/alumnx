"""Database models.

Two tables:
  * Task           — the graded Task API records (§5).
  * EmailDecision  — one row per email we *process*, including skipped ones.
                     This is the ground truth the chat interface queries so it
                     never has to re-call Gemini for facts it already computed.
"""
import datetime as dt
import secrets

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    Integer,
    String,
    Text,
    UniqueConstraint,
)

from .database import Base


def _now_ist_iso() -> str:
    tz = dt.timezone(dt.timedelta(hours=5, minutes=30))
    return dt.datetime.now(tz).isoformat(timespec="seconds")


def _task_id() -> str:
    return "tsk_" + secrets.token_hex(3)


class Task(Base):
    __tablename__ = "tasks"

    # Dedup guard: one task per (candidate, source email). Enforcing this in the
    # DB is what makes the idempotency run (Run 2) pass even under retries.
    __table_args__ = (
        UniqueConstraint("candidate_id", "source_email_id", name="uq_candidate_source"),
    )

    task_id = Column(String, primary_key=True, default=_task_id)
    candidate_id = Column(String, nullable=False, index=True)
    source_email_id = Column(String, nullable=False, index=True)
    thread_id = Column(String, nullable=False, index=True)

    title = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    assignee_id = Column(String, nullable=False)
    category = Column(String, nullable=False)
    priority = Column(String, nullable=False)
    due_date = Column(String, nullable=True)          # YYYY-MM-DD or null
    deal_value_inr = Column(Integer, nullable=True)   # rupees or null
    company_name = Column(String, nullable=True)
    confidence = Column(Float, nullable=False, default=0.5)

    # How many times this task has been PATCHed via a thread reply.
    update_count = Column(Integer, nullable=False, default=0)

    created_at = Column(String, nullable=False, default=_now_ist_iso)
    updated_at = Column(String, nullable=False, default=_now_ist_iso)

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "candidate_id": self.candidate_id,
            "source_email_id": self.source_email_id,
            "thread_id": self.thread_id,
            "title": self.title,
            "description": self.description,
            "assignee_id": self.assignee_id,
            "category": self.category,
            "priority": self.priority,
            "due_date": self.due_date,
            "deal_value_inr": self.deal_value_inr,
            "company_name": self.company_name,
            "confidence": self.confidence,
            "update_count": self.update_count,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class EmailDecision(Base):
    """Audit row for every processed email — the chat interface's data source."""

    __tablename__ = "email_decisions"
    __table_args__ = (
        UniqueConstraint("candidate_id", "email_id", name="uq_candidate_email"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    candidate_id = Column(String, nullable=False, index=True)
    email_id = Column(String, nullable=False, index=True)
    thread_id = Column(String, nullable=True, index=True)
    run_id = Column(String, nullable=True, index=True)

    # decision: "created" | "updated" | "skipped"
    decision = Column(String, nullable=False, index=True)
    category = Column(String, nullable=True, index=True)   # incl. skip reasons
    priority = Column(String, nullable=True)
    assignee_id = Column(String, nullable=True)
    confidence = Column(Float, nullable=True)
    is_spurious_risk = Column(Integer, nullable=False, default=0)  # bool as int
    reasoning = Column(Text, nullable=True)
    task_id = Column(String, nullable=True, index=True)

    # Raw fields kept for the frontend's "render as table" view.
    from_name = Column(String, nullable=True)
    from_email = Column(String, nullable=True)
    subject = Column(String, nullable=True)
    received_at = Column(String, nullable=True)

    created_at = Column(DateTime, default=dt.datetime.utcnow)

    def to_dict(self) -> dict:
        return {
            "email_id": self.email_id,
            "thread_id": self.thread_id,
            "run_id": self.run_id,
            "decision": self.decision,
            "category": self.category,
            "priority": self.priority,
            "assignee_id": self.assignee_id,
            "confidence": self.confidence,
            "reasoning": self.reasoning,
            "task_id": self.task_id,
            "from_name": self.from_name,
            "from_email": self.from_email,
            "subject": self.subject,
            "received_at": self.received_at,
        }
