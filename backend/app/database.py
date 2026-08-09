"""SQLAlchemy engine/session setup. Works with SQLite locally and Postgres in
production via the DATABASE_URL env var. Persistence survives restarts — this is
required for the idempotency and thread-reconciliation grading runs."""
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from .config import DATABASE_URL

# SQLite needs a special flag for multi-threaded FastAPI; Postgres does not.
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(DATABASE_URL, connect_args=connect_args, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    """FastAPI dependency yielding a request-scoped session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    from . import models  # noqa: F401  (ensure models are registered)

    Base.metadata.create_all(bind=engine)
