"""
app.py — FastAPI + Slack Bolt entry point for the ICS Decision Acceleration Tool.

Architecture:
  - FastAPI handles all HTTP traffic (Slack events, interactivity, internal endpoints).
  - Slack Bolt's SlackRequestHandler is mounted as a sub-application at /slack.
  - Internal endpoints (e.g. /internal/run_sla_checks) are protected by a shared secret.

Run locally:
  uvicorn app:api --reload --port 8000
"""
from __future__ import annotations

import logging
import os

from fastapi import FastAPI, Request, Response, HTTPException, Depends
from fastapi.responses import JSONResponse
from slack_bolt import App
from slack_bolt.adapter.fastapi import SlackRequestHandler

import config  # validates env vars at import time
from handlers.commands import handle_decision_command
from handlers.modals import handle_intake_submission, handle_resolution_submission
from handlers.actions import (
    handle_hitl_approve,
    handle_hitl_request_info,
    handle_hitl_edit_draft,
    handle_edit_draft_submission,
    handle_make_decision,
)
from handlers.sla import run_sla_checks as _run_sla_checks
from utils.slack_ui import INTAKE_MODAL_ID, RESOLUTION_MODAL_ID, EDIT_DRAFT_MODAL_ID

# ── Logging ────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)

# ── Slack Bolt app ─────────────────────────────────────────────────────────
bolt_app = App(
    token=config.SLACK_BOT_TOKEN,
    signing_secret=config.SLACK_SIGNING_SECRET,
    # process_before_response=True is required when running behind a web framework
    # so Bolt can acknowledge Slack's 3-second timeout immediately.
    process_before_response=True,
)

# The handler bridges FastAPI requests → Bolt's internal dispatch
bolt_handler = SlackRequestHandler(bolt_app)

# ── FastAPI app ────────────────────────────────────────────────────────────
api = FastAPI(
    title="ICS Decision Acceleration Tool",
    version="1.0.0",
    docs_url=None,   # disable Swagger UI in prod; re-enable locally as needed
    redoc_url=None,
)


# ── Slack event / command / interactivity routes ───────────────────────────

@api.post("/slack/events")
async def slack_events(req: Request) -> Response:
    """Receives Slack Events API payloads (app_mention, message, etc.)."""
    return await bolt_handler.handle(req)


@api.post("/slack/commands")
async def slack_commands(req: Request) -> Response:
    """Receives Slack slash-command payloads (e.g. /decision)."""
    return await bolt_handler.handle(req)


@api.post("/slack/interactivity")
async def slack_interactivity(req: Request) -> Response:
    """Receives Slack interactive component payloads (buttons, modals, etc.)."""
    return await bolt_handler.handle(req)


# ── Internal API — guarded by a shared secret ─────────────────────────────

_INTERNAL_SECRET = os.getenv("INTERNAL_API_SECRET", "")


def _verify_internal(req: Request) -> None:
    """Simple bearer-token guard for internal endpoints."""
    if not _INTERNAL_SECRET:
        # Secret not configured → only allow requests from localhost
        host = req.client.host if req.client else ""
        if host not in ("127.0.0.1", "::1", "localhost"):
            raise HTTPException(status_code=403, detail="Forbidden")
        return

    auth = req.headers.get("Authorization", "")
    if auth != f"Bearer {_INTERNAL_SECRET}":
        raise HTTPException(status_code=403, detail="Forbidden")


@api.post("/internal/run_sla_checks")
async def run_sla_checks(req: Request, _: None = Depends(_verify_internal)):
    """
    SLA cron endpoint.
    Call on a regular schedule (e.g. every 30 min during business hours) via
    an external scheduler, cloud cron, or GitHub Actions workflow.

    Recommended cron: every 30 minutes, Mon–Fri 07:00–19:00 America/Los_Angeles.
    """
    from slack_sdk import WebClient
    slack_client = WebClient(token=config.SLACK_BOT_TOKEN)
    nudges_sent = _run_sla_checks(slack_client)
    return JSONResponse({"status": "ok", "nudges_sent": nudges_sent})


# ── Health check ───────────────────────────────────────────────────────────

@api.get("/health")
async def health() -> JSONResponse:
    return JSONResponse({"status": "ok"})


# ── Bolt listeners ─────────────────────────────────────────────────────────
# All registrations live here so the full listener graph is auditable in one
# place. Heavy logic is delegated to handlers/.

# Slash commands
bolt_app.command("/decision")(handle_decision_command)

# Modal submissions
bolt_app.view(INTAKE_MODAL_ID)(handle_intake_submission)
bolt_app.view(RESOLUTION_MODAL_ID)(handle_resolution_submission)
bolt_app.view(EDIT_DRAFT_MODAL_ID)(handle_edit_draft_submission)

# Interactive button actions
bolt_app.action("hitl_approve")(handle_hitl_approve)
bolt_app.action("hitl_request_info")(handle_hitl_request_info)
bolt_app.action("hitl_edit_draft")(handle_hitl_edit_draft)
bolt_app.action("make_decision")(handle_make_decision)

logger.info(
    "ICS Decision Tool starting — channel=%s, HITL=%s",
    config.DECISIONS_CHANNEL,
    config.HITL_REVIEWER_SLACK_ID,
)
