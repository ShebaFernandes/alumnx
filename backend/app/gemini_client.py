"""Thin wrapper around Gemini with retry/backoff and graceful degradation.

If the key is missing or every retry fails, callers get a clear failure and can
fall back to routing the email to triage rather than dropping it — a dropped
email is worse than a slow one (§8.5)."""
import json
import re
import time
from typing import Optional

from .config import GEMINI_API_KEY, GEMINI_MODEL

_model = None


def _get_model():
    global _model
    if _model is not None:
        return _model
    if not GEMINI_API_KEY:
        return None
    import google.generativeai as genai

    genai.configure(api_key=GEMINI_API_KEY)
    _model = genai.GenerativeModel(GEMINI_MODEL)
    return _model


def available() -> bool:
    return bool(GEMINI_API_KEY)


def generate_json(prompt: str, retries: int = 3) -> Optional[dict]:
    """Call Gemini, parse a JSON object from the reply. Returns None on failure
    after exhausting retries (caller decides how to degrade)."""
    model = _get_model()
    if model is None:
        return None

    last_err = None
    for attempt in range(retries):
        try:
            resp = model.generate_content(
                prompt,
                generation_config={"temperature": 0.1, "response_mime_type": "application/json"},
            )
            text = (resp.text or "").strip()
            return _extract_json(text)
        except Exception as e:  # noqa: BLE001 - broad on purpose for backoff
            last_err = e
            # Exponential backoff for rate limits / transient errors.
            time.sleep(min(2 ** attempt, 8))
    print(f"[gemini] giving up after {retries} attempts: {last_err}")
    return None


def generate_text(prompt: str, retries: int = 3) -> Optional[str]:
    model = _get_model()
    if model is None:
        return None
    last_err = None
    for attempt in range(retries):
        try:
            resp = model.generate_content(prompt, generation_config={"temperature": 0.2})
            return (resp.text or "").strip()
        except Exception as e:  # noqa: BLE001
            last_err = e
            time.sleep(min(2 ** attempt, 8))
    print(f"[gemini] text giving up: {last_err}")
    return None


def _extract_json(text: str) -> Optional[dict]:
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Sometimes wrapped in ```json ... ``` fences.
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            return None
    return None
