# Sales Inbox → Task Router

**candidate_id:** `shebafernandes5@gmail.com`

**Deployed URLs** (fill in after deploying — must be byte-identical to the submission form):

| | URL |
|---|---|
| Backend (base URL — Task API + `/ingest` + `/api/*`) | `https://YOUR-BACKEND.onrender.com` |
| Frontend (conversational interface) | `https://YOUR-FRONTEND.vercel.app` |

> Everything the grader calls lives under the **single backend URL** above:
> `/tasks`, `/users`, `/ingest`, `/api/tasks`, `/api/stats`, `/api/chat`.

---

## What this is

An agent that turns a messy `sales@` inbox into correctly-assigned tasks, plus a
conversational screen where the ops team can see the batch and ask grounded
questions about it.

```
Frontend (React/Vite)  ──►  Backend (FastAPI, one URL)  ──►  DB (SQLite / Postgres)
  paste JSON                 ├─ Task API: /tasks, /users        (survives restarts)
  render table               ├─ /ingest  (email → route → write)
  chat panel                 ├─ /api/tasks /api/stats /api/emails
                             └─ /api/chat (question → SQL → phrasing)
                                       │
                                       └──► Gemini (server-side only)
```

- **Routing** = cheap deterministic skip filters → Gemini classification → rule
  overrides applied in code (72h deadline, PSU→Aarti, value threshold, INR
  parsing). See [`backend/app/routing.py`](backend/app/routing.py).
- **Persistence** = real DB (SQLite locally, Postgres in prod). Dedup on
  `(candidate_id, source_email_id)` gives idempotency; thread replies PATCH the
  existing task instead of creating a new one.
- **Chat is grounded**: every number comes from a SQL query over our own stored
  `email_decisions` table; Gemini only phrases the answer. Zero-count and
  out-of-scope questions are handled explicitly (no hallucinated numbers).

---

## Run it locally (3 commands)

**Backend:**
```bash
cd backend && pip install -r requirements.txt && cp .env.example .env
# put your GEMINI_API_KEY in .env, then:
uvicorn app.main:app --reload --port 8000
```

**Frontend:**
```bash
cd frontend && npm install && cp .env.example .env
npm run dev   # http://localhost:5173
```

That's it. Without a Gemini key the backend still runs — unclassifiable emails
degrade to `u_triage` rather than being dropped (a dropped email is worse than a
slow one). Deterministic skips (spam/OOO/newsletter) work with no key at all.

### Tests
```bash
cd backend && python -m pytest -q
```
Covers the graded mechanics: INR parsing, quote stripping, deadline math, skip
filters, the exact `400 invalid_enum_value` shape, dedup/idempotency, and
candidate_id normalisation.

---

## Environment variables

Backend (`backend/.env`, see `.env.example`):

| Var | Purpose |
|---|---|
| `GEMINI_API_KEY` | Your Gemini key (free tier). Server-side only, never committed. |
| `GEMINI_MODEL` | Default `gemini-1.5-flash`. |
| `DATABASE_URL` | `sqlite:///./app.db` locally; a Postgres URL (Supabase) in prod. |
| `CORS_ORIGINS` | Comma-separated allowed origins; set your Vercel URL in prod. |

Frontend (`frontend/.env`):

| Var | Purpose |
|---|---|
| `VITE_API_BASE` | Base URL of the deployed backend. |
| `VITE_CANDIDATE_ID` | `shebafernandes5@gmail.com` |

**No secrets are committed.** The Gemini key is only ever read server-side and is
never reachable from the browser network tab.

---

## Deploy

**Backend → Render** (`backend/render.yaml` is included):
1. New Web Service → point at this repo, root dir `backend`.
2. Set `GEMINI_API_KEY`, `DATABASE_URL` (Supabase Postgres), `CORS_ORIGINS`.
3. Start command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`.

Use Postgres (Supabase) in production, not SQLite — the idempotency and thread
runs happen minutes apart and must survive a cold restart.

**Frontend → Vercel:** import repo, root dir `frontend`, set `VITE_API_BASE` to
the Render URL and `VITE_CANDIDATE_ID`. Build `npm run build`, output `dist`.

---

## API reference (all under one base URL)

Task API (§5 — graded directly):
- `POST /tasks` · `PATCH /tasks/{id}` · `GET /tasks?candidate_id=` · `DELETE /tasks/{id}` · `GET /users`

Backend wrapper (§7):
- `POST /ingest` — synchronous batch: returns
  `{processed, tasks_created, tasks_updated, skipped, errors}` only after every
  task is written.
- `GET /api/tasks` · `GET /api/emails` · `GET /api/stats`
- `POST /api/chat` — `{answer, supporting_data}`
- `GET /api/sample-emails?count=250` — generate a sample batch

See [`DECISIONS.md`](DECISIONS.md) for engineering tradeoffs and
[`EVALS.md`](EVALS.md) for the labelled eval set and known failure cases.
