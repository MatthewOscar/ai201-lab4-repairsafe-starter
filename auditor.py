import json
import os
from datetime import datetime, timezone
from config import LOG_FILE, LLM_MODEL

# How much of each field we keep. Questions are short, so 300 chars captures
# essentially every real question; 200 chars of response is enough to identify
# which answer was given. See specs/auditor-spec.md for the reasoning.
QUESTION_LIMIT = 300
RESPONSE_PREVIEW_LIMIT = 200

# Keep the one-line terminal summary from wrapping.
CONSOLE_QUESTION_LIMIT = 60


def _truncate(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[:limit]


def log_interaction(question: str, tier: str, response: str) -> None:
    """
    Append a structured record of this interaction to the audit log.

    Writes one JSON object per line to LOG_FILE (.jsonl format), creating the
    logs/ directory first if needed, then prints a one-line terminal summary.
    See specs/auditor-spec.md for the field choices and truncation reasoning.

    Output: None. Side effects only (writes to file, prints to terminal). A
    logging failure warns but never raises, so it cannot crash the request.
    """
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "tier": tier,
        "question": _truncate(question, QUESTION_LIMIT),
        "response_preview": _truncate(response, RESPONSE_PREVIEW_LIMIT),
        "model": LLM_MODEL,
        "response_chars": len(response),
        "question_chars": len(question),
    }

    try:
        # Create logs/ on first run (or a fresh deploy) before appending.
        os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError as e:
        # Accountability layer must not take down the user-facing answer.
        print(f"[LOG ERROR] could not write to {LOG_FILE}: {e}")
        return

    short_q = _truncate(question, CONSOLE_QUESTION_LIMIT)
    if len(question) > CONSOLE_QUESTION_LIMIT:
        short_q += "…"
    print(f'[LOGGED] tier={tier} | "{short_q}" → {len(response)} chars')
