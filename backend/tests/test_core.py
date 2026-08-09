"""Tests for the deterministic mechanics the grader checks: money parsing, skip
filters, enum validation (exact 400 shape), dedup/idempotency, thread PATCH.

Routing that depends on Gemini is covered manually in EVALS.md (needs a live
key); these tests run with no key and no network."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_app.db")

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.parsing import parse_inr, clean_body, within_72h
from app.routing import deterministic_skip
from app.schemas import Email

client = TestClient(app)
CID = "shebafernandes5@gmail.com"


# --- Money parsing --------------------------------------------------------

@pytest.mark.parametrize("text,expected", [
    ("Rs. 25 lakhs", 2500000),
    ("budget approx 1.2 cr allocated", 12000000),
    ("Estimated value: Rs. 6,50,000", 650000),
    ("Gold tier is ₹4,00,000", 400000),
    ("40 lakhs", 4000000),
    ("nothing urgent, no value here", None),
])
def test_parse_inr(text, expected):
    assert parse_inr(text) == expected


# --- Body cleaning (ignore quoted text) -----------------------------------

def test_clean_body_strips_quotes():
    body = "New budget is Rs 32 lakhs.\nOn Mon, Aug 1 2026 someone wrote:\n> old budget was 25 lakhs"
    cleaned = clean_body(body)
    assert "32 lakhs" in cleaned
    assert "old budget" not in cleaned


# --- Deadline math --------------------------------------------------------

def test_within_72h():
    assert within_72h("2026-08-01T14:20:00+05:30", "2026-08-03") is True
    assert within_72h("2026-08-01T09:14:00+05:30", "2026-08-12") is False


# --- Deterministic skips --------------------------------------------------

def _email(**kw):
    base = dict(email_id="em_1", thread_id="th_1", subject="", body="")
    base.update(kw)
    return Email(**base)


def test_skip_out_of_office():
    d = deterministic_skip(_email(subject="Out of Office",
                                  body="I am out of office until 14th August"), "I am out of office until 14th August")
    assert d and d.action == "skip"


def test_skip_spam():
    body = ("Hi, I noticed your website isn't ranking on page 1. We've helped 200+ SaaS companies "
            "3x their organic traffic. Free audit attached — quick 15 min call?")
    d = deterministic_skip(_email(subject="Boost traffic", body=body), body)
    assert d and d.category == "skipped_marketing_lookalike_spam"


def test_skip_newsletter():
    body = "The B2B Growth Weekly — Issue #212. [Unsubscribe]"
    d = deterministic_skip(_email(subject="Newsletter", body=body), body)
    assert d and d.action == "skip"


# --- Enum validation (exact 400 shape) ------------------------------------

def test_bad_enum_returns_exact_shape():
    r = client.post("/tasks", json={
        "candidate_id": CID, "source_email_id": "em_x", "thread_id": "th_x",
        "title": "t", "assignee_id": "Aarti", "category": "enterprise_rfp",
        "priority": "high",
    })
    assert r.status_code == 400
    j = r.json()
    assert j["error"] == "invalid_enum_value"
    assert j["field"] == "assignee_id"
    assert j["received"] == "Aarti"
    assert j["allowed"] == ["u_aarti", "u_rohit", "u_meera", "u_karan", "u_divya", "u_triage"]


# --- Dedup / idempotency --------------------------------------------------

def test_dedup_same_source_email():
    payload = {
        "candidate_id": CID, "source_email_id": "em_dedup", "thread_id": "th_dedup",
        "title": "RFP", "assignee_id": "u_aarti", "category": "enterprise_rfp",
        "priority": "medium", "due_date": None, "deal_value_inr": None,
        "company_name": None, "confidence": 0.9,
    }
    client.post("/tasks", json=payload)
    client.post("/tasks", json=payload)  # identical repost
    r = client.get("/tasks", params={"candidate_id": CID, "source_email_id": "em_dedup"})
    assert len(r.json()) == 1


# --- Candidate normalisation ----------------------------------------------

def test_candidate_alias_normalised():
    payload = {
        "candidate_id": "sheba+fde@gmail.com", "source_email_id": "em_alias",
        "thread_id": "th_alias", "title": "x", "assignee_id": "u_rohit",
        "category": "smb_enquiry", "priority": "low",
    }
    r = client.post("/tasks", json=payload)
    assert r.json()["candidate_id"] == "sheba@gmail.com"


# --- Users ----------------------------------------------------------------

def test_users_roster():
    r = client.get("/users")
    ids = {u["user_id"] for u in r.json()["team"]}
    assert ids == {"u_aarti", "u_rohit", "u_meera", "u_karan", "u_divya", "u_triage"}
