"""The routing brain.

Pipeline per email:
  1. Deterministic skip filters (out-of-office / newsletter / vendor spam).
     These NEVER become tasks — spurious tasks are the most heavily penalised
     outcome (§8.2), so we catch obvious noise cheaply before spending an LLM
     call.
  2. Gemini classification for everything else, returning a structured routing
     decision + short reasoning.
  3. Deterministic rule overrides applied in code (not trusted to the LLM):
     72h deadline -> high, PSU/gov tender -> Aarti, value threshold sanity,
     money parsing. These are the rules that examples 1/3/4/12 hinge on.

The result is a `RoutingDecision`: either skip (with a reason) or a task payload.
"""
import re
from dataclasses import dataclass, field
from typing import Optional

from . import gemini_client
from .config import CATEGORIES, DEAL_VALUE_THRESHOLD_INR
from .parsing import clean_body, parse_inr, within_72h


@dataclass
class RoutingDecision:
    action: str  # "create" | "skip"
    reason: str = ""             # skip reason or classification note
    category: Optional[str] = None
    assignee_id: Optional[str] = None
    priority: Optional[str] = None
    due_date: Optional[str] = None
    deal_value_inr: Optional[int] = None
    company_name: Optional[str] = None
    confidence: float = 0.5
    title: str = ""
    description: str = ""
    is_spurious_risk: bool = False
    extras: dict = field(default_factory=dict)


# --------------------------------------------------------------------------
# Step 1 — deterministic skip filters
# --------------------------------------------------------------------------

_OOO_PATTERNS = [
    r"\bout of office\b",
    r"\bon (?:annual |medical )?leave\b",
    r"\bauto[- ]?reply\b",
    r"\bautomatic reply\b",
    r"\bi am currently (?:away|travelling|traveling)\b",
    r"\bwill be back (?:on|after)\b",
    r"\blimited access to (?:my )?email\b",
]

_NEWSLETTER_PATTERNS = [
    r"\bunsubscribe\b",
    r"\bview (?:this|in) (?:email )?(?:in your )?browser\b",
    r"\bissue #?\d+\b",
    r"\bweekly (?:digest|newsletter|roundup)\b",
    r"\byou(?:'re| are) receiving this (?:email|newsletter)\b",
]

# Vendor spam: they are selling TO us. Direction of intent matters (Example 8).
_SPAM_PATTERNS = [
    r"\bnoticed your (?:website|site) (?:isn'?t|is not) ranking\b",
    r"\bwe(?:'ve| have) helped \d+\+? ",
    r"\bfree audit\b",
    r"\b3x your (?:organic )?traffic\b",
    r"\bboost your (?:seo|rankings|traffic)\b",
    r"\bquick 15[- ]?min(?:ute)? call\b",
    r"\bincrease your (?:sales|revenue|leads) by\b",
    r"\bwe special[iz]se in (?:seo|link building|lead generation)\b",
]


def _matches_any(text: str, patterns) -> Optional[str]:
    for p in patterns:
        if re.search(p, text, re.IGNORECASE):
            return p
    return None


def deterministic_skip(email, body: str) -> Optional[RoutingDecision]:
    """Return a skip decision if the email is obvious noise, else None."""
    subject = (email.subject or "")
    haystack = f"{subject}\n{body}"

    if _matches_any(haystack, _OOO_PATTERNS) or "out of office" in subject.lower():
        return RoutingDecision(action="skip", reason="out_of_office", category="skipped_ooo")

    if _matches_any(haystack, _NEWSLETTER_PATTERNS):
        return RoutingDecision(action="skip", reason="newsletter", category="skipped_newsletter")

    if _matches_any(haystack, _SPAM_PATTERNS):
        return RoutingDecision(
            action="skip",
            reason="vendor_spam",
            category="skipped_marketing_lookalike_spam",
        )
    return None


# --------------------------------------------------------------------------
# Step 2 — Gemini classification
# --------------------------------------------------------------------------

CLASSIFY_PROMPT = """You are a routing engine for a B2B company's sales@ inbox.
Classify ONE email into a task assignment. Return a strict JSON object only.

TEAM (assignee_id -> what they get):
- u_aarti  : RFPs, RFIs, tenders, inbound deals ABOVE Rs 10,00,000 (10 lakh).
- u_rohit  : Product enquiries, demo requests, deals AT OR BELOW Rs 10 lakh.
- u_meera  : Webinars, event/conference sponsorships, content collaborations, PR and media.
- u_karan  : Reseller, channel partner, technology integration proposals (partnerships).
- u_divya  : Invoices, purchase orders, payment reminders, GST and vendor billing.
- u_triage : Ambiguous items, or two distinct asks owned by different people, or missing info needed to route.

category MUST be one of: enterprise_rfp, smb_enquiry, marketing, alliances, finance, triage.
priority MUST be one of: high, medium, low.

CRITICAL JUDGEMENT RULES:
- Direction of intent matters. If the sender is SELLING to us (SEO/marketing agency pitching services), that is spam -> set "skip": true. We only create tasks for people who want to buy from us, partner with us, or bill us.
- Money mentioned does NOT mean Sales. A sponsorship fee -> marketing (u_meera). An invoice amount -> finance (u_divya), and it is NOT a deal_value.
- Government / PSU tenders (e.g. BHEL, ONGC, SAIL, "Tender Notice No.") ALWAYS go to u_aarti regardless of value.
- deal_value_inr is the size of a potential DEAL only. Invoice amounts, sponsorship fees, budgets-for-something-else are not deal values unless clearly a purchase of our product.
- NEVER invent a due_date, deal_value_inr, or company_name. Use null if not clearly stated. "sometime next week" is NOT a due_date.
- Two distinct asks owned by different departments, or "budget TBD" so the value rule can't apply -> u_triage with low confidence and a clear reason.

Output JSON schema (return exactly these keys):
  skip          -> boolean
  skip_reason   -> string or null
  category      -> one of the categories above
  assignee_id   -> one of the assignee ids above
  priority      -> high | medium | low
  due_date      -> "YYYY-MM-DD" or null
  deal_value_inr-> integer or null
  company_name  -> string or null
  confidence    -> number 0.0-1.0
  title         -> short task title
  reasoning     -> one sentence why

EMAIL:
"""


def _classify_with_gemini(email, body: str) -> Optional[dict]:
    # Build the dynamic block with concatenation, NOT str.format — the prompt
    # above intentionally contains no brace-placeholders so nothing can collide
    # with JSON braces.
    email_block = (
        f"Subject: {email.subject or ''}\n"
        f"From: {email.from_name or ''} <{email.from_email or ''}>\n"
        f"Received: {email.received_at or ''}\n"
        f"Body:\n{body[:4000]}\n"
    )
    return gemini_client.generate_json(CLASSIFY_PROMPT + email_block)


# --------------------------------------------------------------------------
# Step 3 — deterministic overrides
# --------------------------------------------------------------------------

_PSU_HINTS = [
    r"\btender notice\b",
    r"\bbhel\b", r"\bongc\b", r"\bsail\b", r"\bntpc\b", r"\bgail\b",
    r"\bbharat heavy electricals\b", r"\bpsu\b",
    r"\bgovernment of\b", r"\bministry of\b", r"\bpublic sector\b",
    r"/proc/", r"\bgem portal\b", r"\be-?procurement\b",
]


def _looks_like_psu_tender(email, body: str) -> bool:
    hay = f"{email.subject or ''}\n{body}"
    return _matches_any(hay, _PSU_HINTS) is not None


def route_email(email) -> RoutingDecision:
    """Full pipeline for a single email object."""
    body = clean_body(email.body or "")

    # Step 1: cheap deterministic skips.
    skip = deterministic_skip(email, body)
    if skip:
        return skip

    # Step 2: Gemini.
    raw = _classify_with_gemini(email, body)

    if raw is None:
        # Graceful degradation: don't drop the email — send it to triage.
        return RoutingDecision(
            action="create",
            category="triage",
            assignee_id="u_triage",
            priority="medium",
            due_date=None,
            deal_value_inr=parse_inr(body),
            company_name=None,
            confidence=0.2,
            title=(email.subject or "Untitled")[:120],
            description="LLM classification unavailable; routed to triage for human review.",
            reason="llm_unavailable",
            is_spurious_risk=False,
        )

    if raw.get("skip"):
        return RoutingDecision(
            action="skip",
            reason=raw.get("skip_reason") or "llm_skip",
            category="skipped_" + (raw.get("skip_reason") or "noise"),
            confidence=float(raw.get("confidence") or 0.5),
        )

    # Normalise / validate LLM output against the allowed enums.
    category = raw.get("category")
    if category not in CATEGORIES:
        category = "triage"
    assignee = raw.get("assignee_id") or "u_triage"

    decision = RoutingDecision(
        action="create",
        category=category,
        assignee_id=assignee,
        priority=raw.get("priority") or "medium",
        due_date=_clean_date(raw.get("due_date")),
        deal_value_inr=_clean_int(raw.get("deal_value_inr")),
        company_name=(raw.get("company_name") or None),
        confidence=float(raw.get("confidence") or 0.5),
        title=(raw.get("title") or email.subject or "Untitled")[:160],
        description=raw.get("reasoning") or "",
        reason=raw.get("reasoning") or "",
    )

    # --- Overrides (code, not LLM) ---------------------------------------

    # Prefer a code-parsed money value if the LLM missed it but text clearly
    # states one; never overwrite a value with a guess.
    if decision.deal_value_inr is None and category in ("enterprise_rfp", "smb_enquiry"):
        parsed = parse_inr(body)
        if parsed is not None:
            decision.deal_value_inr = parsed

    # Rule 3: PSU/government tenders always to Aarti.
    if _looks_like_psu_tender(email, body):
        decision.assignee_id = "u_aarti"
        decision.category = "enterprise_rfp"

    # Value threshold sanity between Aarti and Rohit (only for clear sales cats).
    if decision.category in ("enterprise_rfp", "smb_enquiry") and decision.deal_value_inr is not None:
        if _looks_like_psu_tender(email, body):
            pass  # PSU override wins regardless of value
        elif decision.deal_value_inr > DEAL_VALUE_THRESHOLD_INR:
            decision.assignee_id = "u_aarti"
            decision.category = "enterprise_rfp"
        else:
            decision.assignee_id = "u_rohit"
            decision.category = "smb_enquiry"

    # Rule 1: stated deadline within 72h -> high, regardless of owner.
    if within_72h(email.received_at, decision.due_date):
        decision.priority = "high"

    return decision


def _clean_date(v) -> Optional[str]:
    if not v or v in ("null", "None"):
        return None
    m = re.match(r"(\d{4}-\d{2}-\d{2})", str(v))
    return m.group(1) if m else None


def _clean_int(v) -> Optional[int]:
    if v in (None, "null", "None", ""):
        return None
    try:
        return int(round(float(v)))
    except (ValueError, TypeError):
        return None
