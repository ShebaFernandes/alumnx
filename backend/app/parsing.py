"""Deterministic helpers: Indian money parsing, HTML/quote stripping, deadline
math. These run in code (not the LLM) so they're cheap and exact."""
import datetime as dt
import re
from typing import Optional


# --- Money ----------------------------------------------------------------

def parse_inr(text: str) -> Optional[int]:
    """Best-effort parse of an Indian rupee amount to an integer number of
    rupees. Handles 'Rs. 25 lakhs', '₹4,00,000', '1.2 cr', '6,50,000'.

    Returns None if nothing confidently parseable is found. We deliberately
    prefer None over a guess — a fabricated deal_value scores worse than null.
    """
    if not text:
        return None
    t = text.lower()

    # crore: "1.2 cr", "2 crore", "1.5 crores"
    m = re.search(r"(?:rs\.?|inr|₹)?\s*([\d,]+(?:\.\d+)?)\s*(?:cr\b|crore?s?)", t)
    if m:
        return int(round(_to_float(m.group(1)) * 1_00_00_000))

    # lakh: "25 lakhs", "6.5 lakh", "Rs 4 lac"
    m = re.search(r"(?:rs\.?|inr|₹)?\s*([\d,]+(?:\.\d+)?)\s*(?:lakhs?|lacs?|lakh)", t)
    if m:
        return int(round(_to_float(m.group(1)) * 1_00_000))

    # Plain grouped number with a currency marker: "Rs. 6,50,000", "₹4,00,000"
    m = re.search(r"(?:rs\.?|inr|₹)\s*([\d][\d,]{3,})", t)
    if m:
        return _to_int(m.group(1))

    return None


def _to_float(s: str) -> float:
    return float(s.replace(",", ""))


def _to_int(s: str) -> Optional[int]:
    try:
        return int(round(float(s.replace(",", ""))))
    except ValueError:
        return None


# --- Body cleaning --------------------------------------------------------

_HTML_TAG = re.compile(r"<[^>]+>")
_QUOTE_MARKERS = [
    r"\nOn .+ wrote:",
    r"\n-{2,} ?Original Message ?-{2,}",
    r"\n_{5,}",
    r"\nFrom:\s.+\nSent:\s",
    r"\n>+ ",
    r"\nBegin forwarded message:",
]


def clean_body(body: str) -> str:
    """Strip HTML and cut off quoted reply chains / forwarded blocks so we route
    on the new message only (Example 10: don't re-extract from quoted text)."""
    if not body:
        return ""
    text = _HTML_TAG.sub(" ", body)
    text = text.replace("&nbsp;", " ").replace("&amp;", "&")
    # Truncate at the earliest quote marker.
    cut = len(text)
    for pat in _QUOTE_MARKERS:
        m = re.search(pat, text)
        if m and m.start() < cut:
            cut = m.start()
    text = text[:cut]
    return re.sub(r"[ \t]+", " ", text).strip()


# --- Deadlines ------------------------------------------------------------

def parse_received(received_at: Optional[str]) -> Optional[dt.datetime]:
    if not received_at:
        return None
    try:
        return dt.datetime.fromisoformat(received_at.replace("Z", "+00:00"))
    except ValueError:
        return None


def within_72h(received_at: Optional[str], due_date: Optional[str]) -> bool:
    """True if due_date is within 72 hours of received_at (Rule 1)."""
    recv = parse_received(received_at)
    if not recv or not due_date:
        return False
    try:
        due = dt.date.fromisoformat(due_date)
    except (ValueError, TypeError):
        return False
    # Treat the due date as end-of-day in the received timezone.
    tz = recv.tzinfo or dt.timezone.utc
    due_dt = dt.datetime.combine(due, dt.time(23, 59), tzinfo=tz)
    delta = due_dt - recv
    return dt.timedelta(0) <= delta <= dt.timedelta(hours=72)
