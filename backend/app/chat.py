"""Grounded chat (§7.3).

The golden rule: numbers come from SQL over our own stored data, never from the
LLM. Gemini only phrases an answer around a `supporting_data` dict we computed.
This is what stops hallucinated counts and makes the same question return the
same answer twice.

Flow:
  1. Compute a full structured snapshot of the batch from the DB (counts,
     group-bys, triage list, spurious rate, deal-value sums, thread history).
  2. Detect out-of-scope / action requests -> decline.
  3. Hand the question + the snapshot to Gemini and ask it ONLY to phrase an
     answer from those numbers. If Gemini is down, fall back to a templated
     answer built from the same snapshot.
"""
import re
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from . import gemini_client, models
from .roster import NAME_BY_ID


# --------------------------------------------------------------------------
# Structured snapshot — the single source of truth for every answer
# --------------------------------------------------------------------------

def build_snapshot(db: Session, candidate_id: str, run_id: Optional[str] = None) -> dict:
    """Structured numeric snapshot. When run_id is given, everything is scoped to
    just that ingest run — this is what the chat uses, so "how many of THESE
    emails" answers about the batch the user just pasted, not the whole DB
    (which also holds the automated grading runs)."""
    dq = db.query(models.EmailDecision).filter_by(candidate_id=candidate_id)
    if run_id:
        dq = dq.filter_by(run_id=run_id)
    decisions = dq.all()

    if run_id:
        # Only the tasks produced by this run's emails.
        run_task_ids = [d.task_id for d in decisions if d.task_id]
        if run_task_ids:
            tasks = (
                db.query(models.Task)
                .filter(models.Task.candidate_id == candidate_id)
                .filter(models.Task.task_id.in_(run_task_ids))
                .all()
            )
        else:
            tasks = []
    else:
        tasks = db.query(models.Task).filter_by(candidate_id=candidate_id).all()

    processed = len(decisions)

    # Task category counts (created/updated tasks only).
    cat_counts = {}
    for t in tasks:
        cat_counts[t.category] = cat_counts.get(t.category, 0) + 1

    # Skip buckets from decisions.
    skip_counts = {}
    spurious = 0
    for d in decisions:
        if d.decision == "skipped":
            skip_counts[d.category or "skipped_other"] = skip_counts.get(d.category or "skipped_other", 0) + 1
        if d.is_spurious_risk:
            spurious += 1

    # Triage tasks with reasons.
    triage = [
        {"task_id": t.task_id, "company_name": t.company_name,
         "confidence": t.confidence, "reason": t.description}
        for t in tasks if t.assignee_id == "u_triage"
    ]

    # High priority + low confidence intersection.
    hi_lo = [
        {"task_id": t.task_id, "confidence": t.confidence, "company_name": t.company_name}
        for t in tasks if t.priority == "high" and (t.confidence or 1) < 0.5
    ]

    # Deal value stats.
    values = [t.deal_value_inr for t in tasks if t.category == "enterprise_rfp"]
    stated = [v for v in values if v is not None]
    total_deal_value = sum(stated)
    rfps_no_value = len([v for v in values if v is None])

    # Thread update history.
    threads_multi = [t.thread_id for t in tasks if (t.update_count or 0) >= 1]

    # Assignee counts.
    assignee_counts = {}
    for t in tasks:
        assignee_counts[t.assignee_id] = assignee_counts.get(t.assignee_id, 0) + 1

    return {
        "processed": processed,
        "tasks_total": len(tasks),
        "category_counts": cat_counts,
        "skip_counts": skip_counts,
        "spurious_count": spurious,
        "spurious_rate": round(spurious / processed, 3) if processed else 0.0,
        "assignee_counts": assignee_counts,
        "triage": triage,
        "high_priority_low_confidence": hi_lo,
        "total_deal_value_inr": total_deal_value,
        "rfps_with_no_stated_value": rfps_no_value,
        "threads_updated_multiple_times": threads_multi,
    }


# --------------------------------------------------------------------------
# Out-of-scope / action detection
# --------------------------------------------------------------------------

_ACTION_PATTERNS = [
    r"\bsend\b.*\bemail\b",
    r"\breply to\b",
    r"\bforward\b",
    r"\bdraft (?:an|a) (?:email|message)\b",
    r"\bschedule\b.*\b(meeting|call)\b",
    r"\bcreate a task\b",
    r"\bassign\b.*\bto\b.*\bnow\b",
    r"\bdelete\b",
]


def is_action_request(query: str) -> bool:
    return any(re.search(p, query, re.IGNORECASE) for p in _ACTION_PATTERNS)


# --------------------------------------------------------------------------
# Answer
# --------------------------------------------------------------------------

PHRASE_PROMPT = """You are a grounded analytics assistant for a sales inbox
router. Answer the user's question using ONLY the numbers in DATA below. Do not
invent any number that is not present in DATA. If DATA does not contain what was
asked, say so plainly and say the count is zero or that you don't have that
breakdown. Keep it to 1-3 sentences.

DATA (the only facts you may use):
{data}

QUESTION: {query}

Reply with a short natural-language answer only."""


def answer(db: Session, candidate_id: str, query: str, run_id: Optional[str] = None) -> dict:
    snapshot = build_snapshot(db, candidate_id, run_id)

    # Action requests are out of scope — decline, don't pretend to act (§8.3).
    if is_action_request(query):
        return {
            "answer": "I can only answer questions about the processed email batch — "
                      "I can't send emails, create tasks, or take actions. "
                      "Try asking about counts, categories, triage, or priorities.",
            "supporting_data": {},
        }

    supporting = _select_supporting_data(query, snapshot)

    # Phrase with Gemini, grounded in `supporting`; fall back to a template.
    phrased = None
    if gemini_client.available():
        phrased = gemini_client.generate_text(
            PHRASE_PROMPT.format(data=_fmt(supporting), query=query)
        )
    if not phrased:
        phrased = _template_answer(query, supporting)

    return {"answer": phrased, "supporting_data": supporting}


def _select_supporting_data(query: str, snap: dict) -> dict:
    """Pick the minimal, relevant slice of the snapshot for this question so the
    supporting_data is a tight, checkable set of numbers."""
    q = query.lower()
    cats = snap["category_counts"]
    skips = snap["skip_counts"]

    data = {}

    if "spurious" in q:
        data["spurious_count"] = snap["spurious_count"]
        data["processed"] = snap["processed"]
        data["spurious_rate"] = snap["spurious_rate"]
        return data

    if "triage" in q:
        data["triage_count"] = len(snap["triage"])
        data["triage_task_ids"] = [t["task_id"] for t in snap["triage"]]
        data["triage"] = snap["triage"]
        return data

    if ("high" in q and ("low" in q or "confidence" in q)):
        data["matches"] = snap["high_priority_low_confidence"]
        return data

    if "deal value" in q or ("total" in q and "rfp" in q):
        data["total_deal_value_inr"] = snap["total_deal_value_inr"]
        data["rfps_with_no_stated_value"] = snap["rfps_with_no_stated_value"]
        return data

    if "thread" in q and ("update" in q or "more than once" in q):
        data["threads_updated_multiple_times"] = snap["threads_updated_multiple_times"]
        return data

    # Marketing vs spam distinction.
    if "marketing" in q or "spam" in q:
        data["marketing"] = cats.get("marketing", 0)
        data["skipped_marketing_lookalike_spam"] = skips.get("skipped_marketing_lookalike_spam", 0)
        if "rfp" in q or "proposal" in q:
            data["enterprise_rfp"] = cats.get("enterprise_rfp", 0)
        return data

    # RFP / proposal counts.
    if "rfp" in q or "proposal" in q:
        data["enterprise_rfp"] = cats.get("enterprise_rfp", 0)
        return data

    # Zero-count trap: a category the user names that we don't track (e.g. "GST
    # refunds"). Answer explicitly zero rather than inventing a number.
    known = {
        "finance": cats.get("finance", 0),
        "alliances": cats.get("alliances", 0),
        "smb": cats.get("smb_enquiry", 0),
        "enquiry": cats.get("smb_enquiry", 0),
        "invoice": cats.get("finance", 0),
    }
    for key, val in known.items():
        if key in q:
            data[key] = val
            return data

    # Nothing matched a known metric -> honest zero for whatever was asked.
    subject = re.sub(r"[^a-z ]", "", q)
    label = "_".join(subject.split()[:4]) or "matches"
    data[f"{label}_count"] = 0
    data["note"] = "No emails in this batch matched that description."
    # Also include the full category breakdown so the answer stays useful.
    data["category_counts"] = cats
    return data


def _template_answer(query: str, data: dict) -> str:
    """Deterministic fallback when Gemini is unavailable."""
    if "triage_count" in data:
        return f"{data['triage_count']} task(s) are sitting in triage."
    if "spurious_rate" in data:
        return (f"{data['spurious_count']} of {data['processed']} processed emails were "
                f"spurious (rate {data['spurious_rate']}).")
    if "total_deal_value_inr" in data:
        return (f"Total stated deal value across open RFPs is ₹{data['total_deal_value_inr']:,}; "
                f"{data['rfps_with_no_stated_value']} RFP(s) had no stated value.")
    if "matches" in data:
        return f"{len(data['matches'])} task(s) are high priority but low confidence."
    if "threads_updated_multiple_times" in data:
        n = len(data["threads_updated_multiple_times"])
        return f"{n} thread(s) were updated after their task was created."
    parts = [f"{k}: {v}" for k, v in data.items() if isinstance(v, int)]
    return ("Based on the stored data — " + ", ".join(parts) + ".") if parts else \
        "I don't have that breakdown for this batch."


def _fmt(data: dict) -> str:
    import json
    return json.dumps(data, ensure_ascii=False, indent=2)
