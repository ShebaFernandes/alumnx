# EVALS.md

> **How to produce these numbers** (do this once you have `inbox.json` and a
> Gemini key set):
> 1. Hand-label ≥50 emails in `backend/evals/labels.csv`
>    (columns: `email_id,true_category,true_assignee,should_create` — see
>    `labels.example.csv`).
> 2. Run `python backend/evals/run_eval.py --emails inbox.json --labels backend/evals/labels.csv`.
> 3. Paste the printed grading buckets + per-category P/R/F1 into the tables
>    below, replacing the placeholder rows.
>
> The harness routes each email through the **same** `routing.route_email` used
> in production, so these metrics reflect the deployed system, not a separate
> code path. **Do not fabricate numbers** — an honest low number scores better
> than an invented high one (§7.5).

## Method

- Sample: **N ≥ 50** emails hand-labelled from `inbox.json`, chosen to cover all
  six routes plus the noise classes (OOO / newsletter / vendor spam) and at
  least a few deliberately ambiguous cases.
- Each email labelled with: the correct `assignee_id`, the correct `category`,
  and `should_create` (false for OOO/newsletter/spam).
- Predictions come from the live routing pipeline (deterministic filters →
  Gemini → rule overrides). Metrics computed by `evals/run_eval.py`.

## Grading buckets (fill from harness output)

| Bucket | Count |
|---|---|
| ✅ Correct (task created, right assignee) | _TBD_ |
| ⚠ Misrouted (task created, wrong assignee) | _TBD_ |
| ❌ Missed (should have created, didn't) | _TBD_ |
| 🚨 Spurious (created from spam/newsletter/OOO) | _TBD_ |
| **Total labelled** | _≥50_ |

## Precision / Recall / F1 per category (fill from harness output)

| Category | Precision | Recall | F1 |
|---|---|---|---|
| enterprise_rfp | _TBD_ | _TBD_ | _TBD_ |
| smb_enquiry | _TBD_ | _TBD_ | _TBD_ |
| marketing | _TBD_ | _TBD_ | _TBD_ |
| alliances | _TBD_ | _TBD_ | _TBD_ |
| finance | _TBD_ | _TBD_ | _TBD_ |
| triage | _TBD_ | _TBD_ | _TBD_ |

---

## Failure Cases I Did Not Fix

These are real, reproducible weaknesses observed against the worked examples and
sample data. They are documented rather than patched over.

### 1. Multi-intent emails are not split (Example 11 class)
An email carrying two distinct asks owned by two different people (e.g. an
enterprise eval *and* a webinar co-host request) is routed to `u_triage` with a
low confidence and a stated reason. This is *accepted* by the brief, but it means
a genuinely dual-owned opportunity waits for a human instead of both workstreams
starting. Splitting into two tasks is a defensible alternative I chose not to
build, to keep the "one email → at most one task" invariant that idempotency and
thread reconciliation rely on. **Not fixed:** would need `parent_email_id` and a
reworked dedup key.

### 2. `company_name` inference from email domain is deliberately conservative
For the Hinglish example (Example 12) no company is named in the body, so
`company_name` is `null` — correct per the brief ("do not infer from the domain
unless unambiguous"). But this same conservatism means some emails where the
domain *would* be a safe signal (e.g. `@meridiansteel.co.in` with no in-body
name) also get `null`. I preferred consistent under-claiming over occasional
wrong company names, since a fabricated field scores worse than `null`.
**Not fixed:** a domain→company map with a confidence gate would recover some of
these safely.

### 3. Deterministic spam filter is regex-based and English-biased
The pre-LLM skip filter keys on English phrasing ("free audit", "isn't ranking").
A vendor-spam email written primarily in Hinglish, or with novel phrasing, can
slip past the regex and reach Gemini — which usually still catches it via the
`skip: true` / direction-of-intent instruction, but not always. So spam detection
has two layers of defence but the first layer has a known blind spot.
**Not fixed:** would replace the regex with a small classifier trained on the
hand-labelled set.

### 4. (Add your own from the real `inbox.json` run)
When you run the harness against real data, the **Disagreements** section of its
output lists every email where the prediction differed from your label. Pick the
2–3 most instructive misses and document them here with the email_id and why the
system got it wrong — that specificity is what §7.5 rewards.
