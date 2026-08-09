"""Central configuration, loaded from environment variables.

Nothing sensitive is ever hardcoded. Secrets (Gemini key, DB URL) come from the
environment / a local .env that is git-ignored.
"""
import os

from dotenv import load_dotenv

load_dotenv()

# --- Database -------------------------------------------------------------
# Default to a local SQLite file so the project runs with zero setup.
# In production set DATABASE_URL to a Postgres string (Supabase, etc.).
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./app.db")

# --- Gemini ---------------------------------------------------------------
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")

# --- CORS -----------------------------------------------------------------
CORS_ORIGINS = [
    o.strip() for o in os.getenv("CORS_ORIGINS", "*").split(",") if o.strip()
]

# Valid enums, kept in one place so validation and prompts stay in sync.
ASSIGNEES = ["u_aarti", "u_rohit", "u_meera", "u_karan", "u_divya", "u_triage"]
CATEGORIES = [
    "enterprise_rfp",
    "smb_enquiry",
    "marketing",
    "alliances",
    "finance",
    "triage",
]
PRIORITIES = ["high", "medium", "low"]

# Deal-value threshold that separates enterprise (Aarti) from SMB (Rohit).
DEAL_VALUE_THRESHOLD_INR = 1_000_000  # Rs 10,00,000
