"""Business logic that sits between the HTTP routes and the DB: task upsert with
dedup, thread reconciliation, and the /ingest batch processor."""
import datetime as dt
from typing import Optional

from sqlalchemy.orm import Session

from . import models
from .roster import NAME_BY_ID
from .routing import route_email


def _now_ist_iso() -> str:
    tz = dt.timezone(dt.timedelta(hours=5, minutes=30))
    return dt.datetime.now(tz).isoformat(timespec="seconds")


def get_task_by_source(db: Session, candidate_id: str, source_email_id: str):
    return (
        db.query(models.Task)
        .filter_by(candidate_id=candidate_id, source_email_id=source_email_id)
        .first()
    )


def get_task_by_thread(db: Session, candidate_id: str, thread_id: str):
    return (
        db.query(models.Task)
        .filter_by(candidate_id=candidate_id, thread_id=thread_id)
        .order_by(models.Task.created_at.asc())
        .first()
    )


def create_task_from_payload(db: Session, payload: dict) -> models.Task:
    """Create a task, deduping on (candidate_id, source_email_id). If one already
    exists for that email, update it instead of inserting a duplicate."""
    existing = get_task_by_source(db, payload["candidate_id"], payload["source_email_id"])
    if existing:
        _apply_updates(existing, payload)
        db.commit()
        db.refresh(existing)
        return existing

    task = models.Task(
        candidate_id=payload["candidate_id"],
        source_email_id=payload["source_email_id"],
        thread_id=payload["thread_id"],
        title=payload["title"],
        description=payload.get("description"),
        assignee_id=payload["assignee_id"],
        category=payload["category"],
        priority=payload["priority"],
        due_date=payload.get("due_date"),
        deal_value_inr=payload.get("deal_value_inr"),
        company_name=payload.get("company_name"),
        confidence=payload.get("confidence", 0.5),
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def _apply_updates(task: models.Task, updates: dict):
    for f in [
        "title", "description", "assignee_id", "category", "priority",
        "due_date", "deal_value_inr", "company_name", "confidence",
    ]:
        if f in updates and updates[f] is not None:
            setattr(task, f, updates[f])
    task.updated_at = _now_ist_iso()


def patch_task(db: Session, task: models.Task, updates: dict, bump_update: bool = False):
    _apply_updates(task, updates)
    if bump_update:
        task.update_count = (task.update_count or 0) + 1
    db.commit()
    db.refresh(task)
    return task


# --------------------------------------------------------------------------
# Ingest — the required synchronous batch endpoint (§7.1)
# --------------------------------------------------------------------------

def process_ingest(db: Session, candidate_id: str, emails, run_id: Optional[str] = None) -> dict:
    processed = created = updated = skipped = 0
    errors = []
    run_id = run_id or dt.datetime.utcnow().strftime("run_%Y%m%d%H%M%S")

    for email in emails:
        processed += 1
        try:
            existing_thread_task = None
            is_reply = bool(getattr(email, "is_reply", False)) or getattr(email, "message_index", 0)
            if is_reply:
                existing_thread_task = get_task_by_thread(db, candidate_id, email.thread_id)

            decision = route_email(email)

            if decision.action == "skip":
                skipped += 1
                _record_decision(db, candidate_id, email, run_id, decision, task_id=None,
                                  decision_kind="skipped")
                continue

            # Thread reply on an existing task -> PATCH, never create (Rule 2).
            if existing_thread_task is not None:
                updates = {
                    "priority": decision.priority,
                    "due_date": decision.due_date,
                    "deal_value_inr": decision.deal_value_inr,
                    "confidence": decision.confidence,
                }
                if decision.description:
                    updates["description"] = decision.description
                patch_task(db, existing_thread_task, updates, bump_update=True)
                updated += 1
                _record_decision(db, candidate_id, email, run_id, decision,
                                 task_id=existing_thread_task.task_id, decision_kind="updated")
                continue

            payload = {
                "candidate_id": candidate_id,
                "source_email_id": email.email_id,
                "thread_id": email.thread_id,
                "title": decision.title or (email.subject or "Untitled"),
                "description": decision.description,
                "assignee_id": decision.assignee_id,
                "category": decision.category,
                "priority": decision.priority,
                "due_date": decision.due_date,
                "deal_value_inr": decision.deal_value_inr,
                "company_name": decision.company_name,
                "confidence": decision.confidence,
            }
            before = get_task_by_source(db, candidate_id, email.email_id)
            task = create_task_from_payload(db, payload)
            if before is None:
                created += 1
                kind = "created"
            else:
                updated += 1
                kind = "updated"
            _record_decision(db, candidate_id, email, run_id, decision,
                             task_id=task.task_id, decision_kind=kind)

        except Exception as e:  # noqa: BLE001 - one bad email shouldn't fail the batch
            errors.append({"email_id": getattr(email, "email_id", "?"), "error": str(e)})

    return {
        "processed": processed,
        "tasks_created": created,
        "tasks_updated": updated,
        "skipped": skipped,
        "errors": errors,
        "run_id": run_id,
    }


def _record_decision(db, candidate_id, email, run_id, decision, task_id, decision_kind):
    """Upsert the audit row that powers the chat interface."""
    row = (
        db.query(models.EmailDecision)
        .filter_by(candidate_id=candidate_id, email_id=email.email_id)
        .first()
    )
    is_spurious = 1 if (decision.action == "skip" and decision_kind != "skipped") else 0
    values = dict(
        thread_id=email.thread_id,
        run_id=run_id,
        decision=decision_kind,
        category=decision.category,
        priority=decision.priority,
        assignee_id=decision.assignee_id,
        confidence=decision.confidence,
        is_spurious_risk=is_spurious,
        reasoning=decision.reason or decision.description,
        task_id=task_id,
        from_name=email.from_name,
        from_email=email.from_email,
        subject=email.subject,
        received_at=email.received_at,
    )
    if row:
        for k, v in values.items():
            setattr(row, k, v)
    else:
        db.add(models.EmailDecision(candidate_id=candidate_id, email_id=email.email_id, **values))
    db.commit()
