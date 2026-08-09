"""Generates sample emails matching the inbox.json schema (§3.1), used by the
frontend's 'generate 250 sample emails' option so the interface is testable
without pasting a real batch."""
import datetime as dt
import random

_COMPANIES = [
    ("Meridian Steel", "meridiansteel.co.in"),
    ("Railyard Logistics", "railyardlogistics.in"),
    ("Halcyon Retail", "halcyonretail.com"),
    ("Zenith Cloud Partners", "zenithcloud.ae"),
    ("Vantage Cloud Services", "vantagecloud.io"),
    ("Nimbus Textiles", "nimbustextiles.co.in"),
    ("Orion Pharma", "orionpharma.in"),
]
_PSU = [("Bharat Heavy Electricals Limited", "bhel.in"),
        ("ONGC", "ongc.co.in"), ("Steel Authority of India", "sail.co.in")]

_FIRST = ["Suresh", "Ankit", "Nandita", "Farhan", "Priya", "Rahul", "Meena", "Vikram", "Sana", "Arjun"]
_LAST = ["Kulkarni", "Bose", "Reddy", "Qureshi", "Nair", "Sharma", "Iyer", "Doshi", "Rao", "Khan"]


def _name():
    return f"{random.choice(_FIRST)} {random.choice(_LAST)}"


def _templates(idx, received):
    """Return a (subject, body, extras) tuple for one of several email types."""
    company, domain = random.choice(_COMPANIES)
    person = _name()
    kind = random.choices(
        ["rfp", "smb", "sponsor", "invoice", "alliance", "ooo", "newsletter", "spam", "psu", "ambiguous"],
        weights=[14, 16, 8, 10, 8, 8, 8, 12, 6, 10],
    )[0]

    if kind == "rfp":
        val = random.choice(["25 lakhs", "1.2 cr", "40 lakhs", "80 lakhs"])
        return (f"RFP - Enterprise platform for {company}",
                f"{company} invites proposals for an enterprise deployment across our units. "
                f"Indicative budget is Rs. {val}. Proposals must reach us by 20th August 2026.",
                company, domain, person)
    if kind == "smb":
        return ("Quick demo request",
                f"Hi, we're a 30-person startup. Can we get a demo sometime next week? "
                f"Nothing urgent. — {person}, {company}", company, domain, person)
    if kind == "sponsor":
        return ("Sponsorship confirmation needed",
                "We're finalising sponsors for the India SaaS Summit. Gold tier is ₹4,00,000 "
                "and includes a keynote. We need confirmation by tomorrow EOD as we're going to print.",
                "India SaaS Summit", "saassummit.in", person)
    if kind == "invoice":
        return ("Invoice INV-2026-0331 overdue",
                "Please find attached invoice INV-2026-0331 for Rs. 1,18,000 (incl. 18% GST) "
                "against PO-88214. Payment terms Net 30, now 12 days overdue.", company, domain, person)
    if kind == "alliance":
        return ("Partnership / reselling enquiry",
                f"We're an implementation partner with 40+ enterprise clients and would like to "
                f"explore reselling your platform, or a technical integration. Who handles partnerships?",
                company, domain, person)
    if kind == "ooo":
        return ("Out of Office",
                "I am out of office until 14th August with limited access to email. "
                "For urgent matters contact my colleague. — Sent from Outlook", company, domain, person)
    if kind == "newsletter":
        return (f"The B2B Growth Weekly — Issue #{200 + idx % 50}",
                "In this edition: why PLG is stalling and 5 pricing experiments that worked. [Unsubscribe]",
                "B2B Growth Weekly", "b2bgrowth.example", person)
    if kind == "spam":
        return ("Boost your organic traffic",
                "Hi, I noticed your website isn't ranking on page 1. We've helped 200+ SaaS companies "
                "3x their organic traffic. We do content marketing, PR outreach, webinar promotion. "
                "Free audit attached — interested in a quick 15 min call?", "GrowthHackers", "seo-agency.example", person)
    if kind == "psu":
        company, domain = random.choice(_PSU)
        return (f"Tender Notice No. {company[:4].upper()}/PROC/2026/{800 + idx}",
                f"{company} invites bids for supply of analytics software licences. "
                f"Estimated value: Rs. 6,50,000. Last date for bid submission: 12-08-2026, 1700 hrs IST.",
                company, domain, person)
    # ambiguous
    return ("Two things after your booth visit",
            f"Hi — we met at your booth. (1) we'd like to evaluate your platform for our 800-person org, "
            f"budget TBD but likely significant, and (2) our CMO wants to co-host a webinar in September. "
            f"Can you loop in the right people? — {person}, VP Strategy, {company}", company, domain, person)


def generate_emails(n: int = 250, seed: int = 42):
    random.seed(seed)
    start = dt.datetime(2026, 8, 1, 9, 0, tzinfo=dt.timezone(dt.timedelta(hours=5, minutes=30)))
    emails = []
    for i in range(n):
        received = start + dt.timedelta(minutes=17 * i)
        subject, body, company, domain, person = _templates(i, received)
        emails.append({
            "email_id": f"em_{i:05d}",
            "thread_id": f"th_{i:04d}",
            "message_index": 0,
            "from_name": person,
            "from_email": f"{person.split()[0].lower()}@{domain}",
            "to": "sales@company.com",
            "cc": [],
            "subject": subject,
            "body": body,
            "received_at": received.isoformat(timespec="seconds"),
            "attachments": [],
            "is_reply": False,
        })
    return emails
