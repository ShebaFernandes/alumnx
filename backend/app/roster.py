"""The team roster (§3.2). Served from GET /users so the frontend never
hardcodes names."""

TEAM = [
    {
        "user_id": "u_aarti",
        "name": "Aarti Menon",
        "department": "Sales — Enterprise",
        "scope": "RFPs, RFIs, tenders, and inbound deals above ₹10,00,000",
    },
    {
        "user_id": "u_rohit",
        "name": "Rohit Sharma",
        "department": "Sales — SMB",
        "scope": "Product enquiries, demo requests, deals at or below ₹10,00,000",
    },
    {
        "user_id": "u_meera",
        "name": "Meera Iyer",
        "department": "Marketing",
        "scope": "Webinars, event and conference sponsorships, content collaborations, PR and media",
    },
    {
        "user_id": "u_karan",
        "name": "Karan Doshi",
        "department": "Alliances",
        "scope": "Reseller, channel partner, and technology integration proposals",
    },
    {
        "user_id": "u_divya",
        "name": "Divya Rao",
        "department": "Finance",
        "scope": "Invoices, purchase orders, payment reminders, GST and vendor billing",
    },
    {
        "user_id": "u_triage",
        "name": "Triage Queue",
        "department": "Operations",
        "scope": "Ambiguous items requiring human review",
    },
]

NAME_BY_ID = {u["user_id"]: u["name"] for u in TEAM}
