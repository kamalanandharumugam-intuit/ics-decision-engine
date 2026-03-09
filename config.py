"""
Central configuration — loaded once at startup from environment variables.
All other modules import from here so there is a single source of truth.
"""
import os
from dotenv import load_dotenv

load_dotenv()


def _require(key: str) -> str:
    value = os.getenv(key)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {key}")
    return value


# ── Slack ──────────────────────────────────────────────────────────────────
SLACK_BOT_TOKEN: str = _require("SLACK_BOT_TOKEN")
SLACK_SIGNING_SECRET: str = _require("SLACK_SIGNING_SECRET")

# ── Anthropic ──────────────────────────────────────────────────────────────
ANTHROPIC_API_KEY: str = _require("ANTHROPIC_API_KEY")
ANTHROPIC_MODEL: str = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6")

# ── Airtable ───────────────────────────────────────────────────────────────
AIRTABLE_API_KEY: str = _require("AIRTABLE_API_KEY")
AIRTABLE_BASE_ID: str = _require("AIRTABLE_BASE_ID")
AIRTABLE_TABLE_NAME: str = os.getenv("AIRTABLE_TABLE_NAME", "Decisions")

# ── App ────────────────────────────────────────────────────────────────────
DECISIONS_CHANNEL: str = os.getenv("DECISIONS_CHANNEL", "#ics-decisions")
HITL_REVIEWER_SLACK_ID: str = _require("HITL_REVIEWER_SLACK_ID")
PORT: int = int(os.getenv("PORT", "8000"))

# ── Timezone ───────────────────────────────────────────────────────────────
TIMEZONE: str = "America/Los_Angeles"
