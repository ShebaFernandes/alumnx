# Sales Inbox → Task Router

An AI agent that reads a messy B2B `sales@` inbox, routes each email to the right
owner (or correctly ignores noise), writes it as a task, and gives the ops team a
screen to watch it happen and ask grounded questions about it.

Built for the Alumnx AI Labs FDE Intern challenge.

---

## Submission details

**candidate_id:** `shebafernandes5@gmail.com`

**Deployed URLs** — *fill these in after deploying; they must be byte-identical to
the submission form:*

| | URL |
|---|---|
| **Backend** (base URL — Task API + `/ingest` + `/api/*`) | `https://YOUR-BACKEND.onrender.com` |
| **Frontend** (conversational interface) | `https://YOUR-FRONTEND.vercel.app` |

> Everything the grader calls lives under the **single backend URL** above —
> `/tasks`, `/users`, `/ingest`, `/api/tasks`, `/api/stats`, `/api/chat`.
> The frontend and backend are deployed separately but the backend is one URL.

---

## What it does

```
Frontend (React/Vite, Vercel)  ──►  Backend (FastAPI, Render — ONE URL)  ──►  Postgres (Supabase)
  paste emails as JSON               ├─ Task API:  /tasks, /users               (survives restarts)
  render them as a table             ├─ /ingest    (email → route → write)
  chat about the batch               ├─ /api/tasks /api/stats /api/emails
                                     └─ /api/chat  (question → SQL → phrasing)
                                               │
                                               └──►  Gemini  (server-side only)
```

Three ideas the whole design is built around:

- **Routing** = cheap deterministic skip filters (spam / out-of-office /
  newsletter) → Gemini classification → business-rule overrides applied in
  **code** (72-hour deadline → high, PSU tender → Aarti, ₹10L value threshold,
  Indian-rupee parsing like "25 lakhs" and "1.2 cr"). The LLM does the fuzzy
  semantic work; code owns the hard invariants.
  See [`backend/app/routing.py`](backend/app/routing.py).
- **Persistence** = a real database (SQLite locally, Postgres in production).
  Tasks are deduplicated on `(candidate_id, source_email_id)`, so re-posting the
  same email **updates** instead of duplicating (idempotency), and a reply on an
  existing thread **PATCHes** the existing task instead of creating a new one.
- **Grounded chat** = every number in an answer comes from a SQL query over our
  own stored decision data; Gemini only phrases the sentence. Zero-count
  questions return **"0"** and action requests are **declined** — the chat can't
  hallucinate a number. Answers are **scoped to the batch you just routed**
  (via `run_id`), so "how many of *these* emails…" reflects that batch, not the
  whole database. See [`backend/app/chat.py`](backend/app/chat.py).

---

## Run it locally

**Backend** (3 commands):
```bash
cd backend && pip install -r requirements.txt && cp .env.example .env
```
Add your `GEMINI_API_KEY` to `backend/.env`, then:
```bash
uvicorn app.main:app --reload --port 8000
```

**Frontend** (3 commands):
```bash
cd frontend && npm install && cp .env.example .env
```
Then:
```bash
npm run dev   # opens http://localhost:5173
```

Without a Gemini key the backend still runs — emails it can't classify degrade to
`u_triage` rather than being dropped (a dropped email is worse than a slow one),
and the deterministic spam/OOO/newsletter filters work with no key at all.

### Tests
```bash
cd backend && python -m pytest -q
```
Covers the graded mechanics: rupee parsing, quoted-reply stripping, the 72-hour
deadline rule, skip filters, the exact `400 invalid_enum_value` shape,
dedup/idempotency, and `candidate_id` normalisation.

---

## Deploy (do this before submitting)

> **Important:** the frontend goes on **Vercel**, but the FastAPI **backend
> cannot run on Vercel** — it needs a always-on Python host. Put the backend on
> **Render** (free) with a **Supabase** Postgres database, and the frontend on
> Vercel. Deploy the backend first so you have its URL for the frontend.

### 1 · Database — Supabase (free Postgres)
1. Create a project at supabase.com.
2. Project → **Settings → Database → Connection string → URI**. Copy it.
3. Convert the scheme for SQLAlchemy: change `postgresql://` to
   `postgresql+psycopg2://`. This is your `DATABASE_URL`.

### 2 · Backend — Render
1. render.com → **New → Web Service** → connect this GitHub repo.
2. **Root Directory:** `backend`
3. **Build Command:** `pip install -r requirements.txt`
4. **Start Command:** `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
5. **Environment variables:**
   - `GEMINI_API_KEY` = your key
   - `GEMINI_MODEL` = `gemini-1.5-flash`
   - `DATABASE_URL` = the Supabase URI from step 1
   - `CORS_ORIGINS` = your Vercel URL (add it after step 3; `*` temporarily)
6. Deploy. Note the URL, e.g. `https://sales-inbox-backend.onrender.com`.
7. Verify it's live: open `<backend-url>/health` → `{"status":"ok"}`.

*(A `backend/render.yaml` blueprint is included if you prefer Render's
"Blueprint" flow.)*

### 3 · Frontend — Vercel
1. vercel.com → **Add New → Project** → import this repo.
2. **Root Directory:** `frontend`
3. Framework preset: **Vite** (Build `npm run build`, Output `dist`).
4. **Environment variables:**
   - `VITE_API_BASE` = your Render backend URL (no trailing slash)
   - `VITE_CANDIDATE_ID` = `shebafernandes5@gmail.com`
5. Deploy. Note the URL, e.g. `https://sales-inbox.vercel.app`.
6. Go back to Render and set `CORS_ORIGINS` to this exact Vercel URL, then
   redeploy the backend.

### 4 · Confirm the two halves talk
Open the frontend, click **Generate 250 sample emails → Route this batch**. You
should see created / skipped counts and be able to ask the chat questions. If the
chat errors, it's almost always `CORS_ORIGINS` on the backend not matching the
Vercel URL.

---

## Environment variables

Backend (`backend/.env`, template in `backend/.env.example`):

| Var | Purpose |
|---|---|
| `GEMINI_API_KEY` | Your Gemini key (free tier). Server-side only, never committed. |
| `GEMINI_MODEL` | Default `gemini-1.5-flash`. |
| `DATABASE_URL` | `sqlite:///./app.db` locally; a Supabase Postgres URI in production. |
| `CORS_ORIGINS` | Comma-separated allowed origins; set to your Vercel URL in production. |

Frontend (`frontend/.env`, template in `frontend/.env.example`):

| Var | Purpose |
|---|---|
| `VITE_API_BASE` | Base URL of the deployed backend. |
| `VITE_CANDIDATE_ID` | `shebafernandes5@gmail.com` |

**No secrets are committed** — `.env` is git-ignored, and the Gemini key is only
ever read server-side, never reachable from the browser network tab.

---

## API reference (all under the one backend URL)

**Task API** (the exact spec the grader calls directly):
- `POST /tasks` — create a task; returns `201`, or `400 invalid_enum_value` on a bad enum
- `PATCH /tasks/{id}` — update a task
- `GET /tasks?candidate_id=…` — list tasks (filters: `thread_id`, `source_email_id`, `assignee_id`)
- `DELETE /tasks/{id}` — delete one task
- `GET /users` — the team roster

**Backend wrapper** (frontend-facing):
- `POST /ingest` — synchronous batch; returns
  `{processed, tasks_created, tasks_updated, skipped, errors}` only after every
  task is written
- `GET /api/tasks` · `GET /api/emails` · `GET /api/stats`
- `POST /api/chat` — returns `{answer, supporting_data}`; accepts an optional
  `run_id` to scope the answer to a single routed batch
- `GET /api/sample-emails?count=250` — generate a sample batch for testing

---

## Submission checklist

- [ ] Deployed backend URL, publicly reachable — includes the Task API (`/tasks`, `/users`), `/ingest`, and `/api/*`
- [ ] Deployed frontend URL, publicly reachable, reading live from the backend
- [ ] Public GitHub repo, setup in ≤3 commands, `.env.example` present, **no committed secrets**
- [ ] `EVALS.md` with ≥50 hand-labelled emails and a "Failure Cases I Did Not Fix" section
- [ ] `DECISIONS.md` with 5 tradeoffs, including the chat-grounding approach
- [ ] `candidate_id` and both deployed URLs at the top of this README — **byte-identical** to the submission form

See [`DECISIONS.md`](DECISIONS.md) for engineering tradeoffs and
[`EVALS.md`](EVALS.md) for the evaluation set and known failure cases.
