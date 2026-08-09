"""FastAPI app exposing everything under ONE base URL (§5 requirement):

  Task API (graded directly by the grader):
    POST   /tasks
    PATCH  /tasks/{task_id}
    GET    /tasks?candidate_id=...
    DELETE /tasks/{task_id}
    GET    /users

  Your backend wrapper (frontend-facing):
    POST   /ingest
    GET    /api/tasks
    GET    /api/stats
    POST   /api/chat
    GET    /api/emails          (raw processed rows for the table view)
    GET    /api/sample-emails   (generate a sample batch)
"""
from fastapi import Depends, FastAPI, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from . import chat, models, service
from .config import CORS_ORIGINS
from .database import get_db, init_db
from .roster import TEAM
from .sample_data import generate_emails
from .schemas import (
    ChatRequest,
    EnumError,
    IngestRequest,
    TaskCreate,
    TaskPatch,
)

app = FastAPI(title="Sales Inbox → Task Router", version="1.0.0")

# Ensure tables exist as soon as the module is imported (covers test clients and
# any WSGI/ASGI server that doesn't fire startup events the same way).
init_db()

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS or ["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def _startup():
    init_db()


# --- Exact 400 shape for bad enums (§5.1) ---------------------------------

@app.exception_handler(EnumError)
async def _enum_error_handler(request: Request, exc: EnumError):
    return JSONResponse(
        status_code=400,
        content={
            "error": "invalid_enum_value",
            "field": exc.field,
            "received": exc.received,
            "allowed": exc.allowed,
        },
    )


# Pydantic wraps validator errors; unwrap our EnumError so the shape is exact.
from fastapi.exceptions import RequestValidationError  # noqa: E402


@app.exception_handler(RequestValidationError)
async def _validation_handler(request: Request, exc: RequestValidationError):
    for err in exc.errors():
        ctx = err.get("ctx", {})
        original = ctx.get("error")
        if isinstance(original, EnumError):
            return JSONResponse(
                status_code=400,
                content={
                    "error": "invalid_enum_value",
                    "field": original.field,
                    "received": original.received,
                    "allowed": original.allowed,
                },
            )
    return JSONResponse(status_code=422, content={"error": "validation_error", "detail": exc.errors()})


@app.get("/")
def root():
    return {"service": "sales-inbox-task-router", "status": "ok"}


@app.get("/health")
def health():
    return {"status": "ok"}


# ==========================================================================
# Task API (§5) — graded directly
# ==========================================================================

@app.post("/tasks", status_code=201)
def create_task(body: TaskCreate, db: Session = Depends(get_db)):
    payload = body.model_dump()
    task = service.create_task_from_payload(db, payload)
    return {
        "task_id": task.task_id,
        "candidate_id": task.candidate_id,
        "source_email_id": task.source_email_id,
        "created_at": task.created_at,
    }


@app.patch("/tasks/{task_id}")
def update_task(task_id: str, body: TaskPatch, db: Session = Depends(get_db)):
    task = db.query(models.Task).filter_by(task_id=task_id).first()
    if not task:
        return JSONResponse(status_code=404, content={"error": "not_found", "task_id": task_id})
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    task = service.patch_task(db, task, updates)
    return task.to_dict()


@app.get("/tasks")
def list_tasks(
    candidate_id: str = Query(...),
    thread_id: str = Query(None),
    source_email_id: str = Query(None),
    assignee_id: str = Query(None),
    db: Session = Depends(get_db),
):
    cid = candidate_id.strip().lower()
    q = db.query(models.Task).filter_by(candidate_id=cid)
    if thread_id:
        q = q.filter_by(thread_id=thread_id)
    if source_email_id:
        q = q.filter_by(source_email_id=source_email_id)
    if assignee_id:
        q = q.filter_by(assignee_id=assignee_id)
    return [t.to_dict() for t in q.all()]


@app.delete("/tasks/{task_id}")
def delete_task(task_id: str, db: Session = Depends(get_db)):
    task = db.query(models.Task).filter_by(task_id=task_id).first()
    if not task:
        return JSONResponse(status_code=404, content={"error": "not_found", "task_id": task_id})
    db.delete(task)
    db.commit()
    return {"deleted": task_id}


@app.get("/users")
def get_users():
    return {"team": TEAM}


# ==========================================================================
# Backend wrapper (§7)
# ==========================================================================

@app.post("/ingest")
def ingest(body: IngestRequest, db: Session = Depends(get_db)):
    result = service.process_ingest(db, body.candidate_id, body.emails, body.run_id)
    return result


@app.get("/api/tasks")
def api_tasks(candidate_id: str = Query(...), db: Session = Depends(get_db)):
    cid = candidate_id.strip().lower()
    tasks = db.query(models.Task).filter_by(candidate_id=cid).all()
    # Join with skip decisions so the UI can show why things were skipped.
    skipped = (
        db.query(models.EmailDecision)
        .filter_by(candidate_id=cid, decision="skipped")
        .all()
    )
    return {
        "tasks": [t.to_dict() for t in tasks],
        "skipped": [d.to_dict() for d in skipped],
    }


@app.get("/api/emails")
def api_emails(candidate_id: str = Query(...), db: Session = Depends(get_db)):
    cid = candidate_id.strip().lower()
    rows = db.query(models.EmailDecision).filter_by(candidate_id=cid).all()
    return {"emails": [d.to_dict() for d in rows]}


@app.get("/api/stats")
def api_stats(candidate_id: str = Query(...), db: Session = Depends(get_db)):
    cid = candidate_id.strip().lower()
    snap = chat.build_snapshot(db, cid)
    # Also break down by run.
    runs = {}
    for d in db.query(models.EmailDecision).filter_by(candidate_id=cid).all():
        r = runs.setdefault(d.run_id or "unknown", {"processed": 0, "created": 0, "updated": 0, "skipped": 0})
        r["processed"] += 1
        if d.decision in ("created", "updated", "skipped"):
            r[d.decision] += 1
    return {
        "processed": snap["processed"],
        "tasks_total": snap["tasks_total"],
        "by_category": snap["category_counts"],
        "by_assignee": snap["assignee_counts"],
        "skipped": snap["skip_counts"],
        "spurious_count": snap["spurious_count"],
        "spurious_rate": snap["spurious_rate"],
        "by_run": runs,
    }


@app.post("/api/chat")
def api_chat(body: ChatRequest, db: Session = Depends(get_db)):
    return chat.answer(db, body.candidate_id, body.query)


@app.get("/api/sample-emails")
def api_sample_emails(count: int = Query(250, ge=1, le=250)):
    return {"emails": generate_emails(count)}
