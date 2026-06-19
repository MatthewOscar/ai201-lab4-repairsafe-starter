import os
from dotenv import load_dotenv

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
LLM_MODEL = "llama-3.3-70b-versatile"
LOG_FILE = "logs/audit.jsonl"
SESSION_SUMMARY_FILE = "logs/session_summary.jsonl"
VALID_TIERS = {"safe", "caution", "refuse", "legal"}
