# DECISIONS.md — engineering tradeoffs

Five tradeoffs, why I made them, and what I'd do with two more weeks.

---

### 1. Deterministic filters *before* the LLM, and rule overrides *after* it

**What:** Obvious noise (out-of-office, newsletters, SEO/vendor spam) is caught
by regex filters in [`routing.py`](backend/app/routing.py) and never reaches
Gemini. Money parsing, the 72-hour deadline rule, the PSU→Aarti rule, and the
₹10L value threshold are applied in **code** on top of the LLM's output.

**Why:** Spurious tasks are the most heavily penalised outcome (§8.2), and the
single most common failure is keyword-matching vendor spam into Marketing
(Example 8). A regex that keys on *direction of intent* ("we noticed your site
isn't ranking", "free audit") is both cheaper and more reliable than trusting the
LLM to never bite. Symmetrically, deterministic rules like "PSU tender always →
Aarti regardless of value" (Example 3) are business invariants — I don't want a
model temperature deciding them. The LLM does the fuzzy semantic work; code owns
the hard rules.

**Two weeks:** Replace brittle regex with a small learned spam classifier trained
on the hand-labelled set, and log every override so I can measure how often the
LLM and the rules disagree.

---

### 2. Idempotency via a DB uniqueness constraint, not app logic

**What:** `tasks` has `UNIQUE(candidate_id, source_email_id)`. `POST /tasks` and
`/ingest` upsert: if a task already exists for that source email, it's updated in
place. Thread replies look up the existing task by `thread_id` and `PATCH` it,
bumping an `update_count`.

**Why:** Runs 2 and 3 (§8.1) post the same/overlapping batches minutes apart and
demand the task count not grow. Enforcing uniqueness at the database layer means
idempotency holds even under retries, concurrent requests, or a process restart —
it can't be defeated by a bug in a Python `if` branch. Verified in tests and a
live 250-email double-ingest: run 2 created 0, updated 180, count unchanged.

**Two weeks:** Add an idempotency key per ingest batch so a client retry of a
whole batch is a no-op, and store a content hash so a genuinely edited resend
(not just a duplicate) can be distinguished from a byte-identical one.

---

### 3. A separate `email_decisions` table as the chat's ground truth

**What:** Every processed email — including skipped ones that never become
tasks — writes a row capturing decision, category, confidence, and reasoning.
The chat and `/api/stats` read only from this table + `tasks`.

**Why:** The Task API has no concept of "skipped" (§7.2), but the ops exec still
needs to see that spam *was seen and correctly ignored*. Storing the full
decision trail means the chat can answer "how many marketing vs. spam we ignored"
by distinguishing a routed `marketing` task from a `skipped_marketing_lookalike_spam`
row — two different buckets — without re-reading a single email body or calling
Gemini for a fact I already computed. This is also what makes answers stable:
the same question twice hits the same rows and returns the same number.

**Two weeks:** Version the decision rows so I can show *why a routing changed*
across runs, and surface a per-email audit view in the UI.

---

### 4. Chat = question → structured query → Gemini phrasing (never LLM-as-database)

**What:** [`chat.py`](backend/app/chat.py) builds a full numeric snapshot from
SQL, selects the minimal relevant slice as `supporting_data`, then asks Gemini to
phrase an answer **using only those numbers**. Action requests ("send an email")
are detected and declined; unknown categories return an explicit zero. If Gemini
is down, a deterministic template answers from the same snapshot.

**Why:** A chat interface that hallucinates a plausible count is worse than none
(§7.3), and grading deliberately probes zero-count and out-of-scope questions.
By computing every number in code and letting the LLM only phrase, a fabricated
number is structurally impossible — the answer is always traceable to
`supporting_data`, which the grader can cross-check. Query path:
`question → keyword routing → SQL aggregate over email_decisions/tasks →
supporting_data dict → Gemini phrases`. Verified live: "GST refunds?" → `0`;
"send Aarti an email" → declined.

**Two weeks:** Replace keyword routing with a constrained tool/function-calling
schema so Gemini *picks* which structured query to run (still executed by me,
still returning real numbers) — more flexible, same anti-hallucination guarantee.

---

### 5. Graceful degradation over strictness when the LLM fails

**What:** If Gemini returns nothing after retries (rate limit, timeout, bad
JSON), the email is routed to `u_triage` with low confidence and a reason, not
dropped. Retries use exponential backoff. One bad email never fails the whole
`/ingest` batch — it's collected into `errors[]`.

**Why:** §8.5 explicitly rewards this: "a dropped email is worse than a slow one."
On a free Gemini tier, transient failures are a *when*, not an *if*. Sending an
uncertain email to a human review queue is the safe, honest failure mode — it
matches exactly what `u_triage` exists for.

**Two weeks:** A proper job queue with per-email retry and a dead-letter table,
so a batch that partially fails can be resumed rather than re-run wholesale, and
rate-limit headroom is respected via a token-bucket limiter.

---

## The one thing I knowingly shipped wrong

**Compound/multi-intent emails are collapsed to a single task.** Example 11 (an
RFP *and* a webinar co-host ask, owned by two different people) is routed to
`u_triage` with a low confidence and a stated reason — which the brief accepts as
correct — but I do **not** split it into two tasks. Splitting is a defensible
alternative the brief allows; I chose single-task-to-triage because it keeps the
idempotency and thread-reconciliation model simple (one email → at most one
task), and because a wrong confident split is more damaging than an honest
"needs a human." The cost: a genuinely dual-owned email sits in triage instead of
progressing both workstreams. With more time I'd support 1-email→N-tasks with a
`parent_email_id` link and reconcile dedup/threading against that.
