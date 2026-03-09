"""
Slash command handlers.

Registered in app.py:
    bolt_app.command("/decision")(handle_decision_command)
"""
from __future__ import annotations

import logging

from slack_bolt import BoltContext
from slack_sdk import WebClient

from utils.slack_ui import build_intake_modal

logger = logging.getLogger(__name__)


def handle_decision_command(
    ack,
    body: dict,
    client: WebClient,
    context: BoltContext,
) -> None:
    """
    Entry point for /decision.

    Subcommands:
      /decision new   — open the intake modal (default if no subcommand given)
      /decision help  — show usage hint
    """
    ack()  # Acknowledge within 3 s to avoid Slack timeout

    text: str = (body.get("text") or "").strip().lower()
    trigger_id: str = body["trigger_id"]

    if text in ("", "new"):
        _open_intake_modal(client, trigger_id)
    elif text == "help":
        _post_help(client, body["channel_id"], body["user_id"])
    else:
        client.chat_postEphemeral(
            channel=body["channel_id"],
            user=body["user_id"],
            text=(
                f"Unknown subcommand `{text}`. "
                "Try `/decision new` to submit a decision or `/decision help` for usage."
            ),
        )


def _open_intake_modal(client: WebClient, trigger_id: str) -> None:
    """Open the decision intake modal."""
    try:
        client.views_open(
            trigger_id=trigger_id,
            view=build_intake_modal(),
        )
        logger.info("Opened intake modal (trigger_id=%s)", trigger_id)
    except Exception as exc:
        logger.error("Failed to open intake modal: %s", exc, exc_info=True)


def _post_help(client: WebClient, channel_id: str, user_id: str) -> None:
    client.chat_postEphemeral(
        channel=channel_id,
        user=user_id,
        text=(
            "*ICS Decision Tool — Usage*\n\n"
            "• `/decision new` — Submit a new decision request\n"
            "• `/decision help` — Show this message\n\n"
            "Decisions are tracked in Airtable and routed automatically. "
            "Max SLA is *4 business days*."
        ),
    )
