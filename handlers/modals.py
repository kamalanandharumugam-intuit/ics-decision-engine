"""
Modal view-submission handlers.

Registered in app.py:
    bolt_app.view(INTAKE_MODAL_ID)(handle_intake_submission)
    bolt_app.view(RESOLUTION_MODAL_ID)(handle_resolution_submission)
"""
from __future__ import annotations

import logging
import threading
from typing import Any

from slack_sdk import WebClient

import config
from utils import airtable_client as at
from utils.airtable_client import (
    F_DRAFT_DUE,
    F_SLA_DEADLINE,
    F_SPONSOR,
    F_DECISION_MAKER,
)
from utils.llm import generate_decision_draft
from utils.slack_ui import (
    INTAKE_MODAL_ID,
    RESOLUTION_MODAL_ID,
    AID_TITLE, BID_TITLE,
    AID_TYPE, BID_TYPE,
    AID_SPONSOR, BID_SPONSOR,
    AID_DECISION_MAKER, BID_DECISION_MAKER,
    AID_CONTEXT, BID_CONTEXT,
    AID_LINKS, BID_LINKS,
    AID_VISIBILITY, BID_VISIBILITY,
    AID_OUTCOME, BID_OUTCOME,
    AID_RATIONALE, BID_RATIONALE,
    build_intake_channel_message,
    build_hitl_dm_message,
    build_closed_thread_message,
)

logger = logging.getLogger(__name__)

# Maps decision type → bot-assigned priority
_PRIORITY_MAP: dict[str, str] = {
    "Strategic": "P0",
    "Investment": "P0",
    "Policy": "P1",
    "Operational": "P1",
    "Other": "P2",
}


# ══════════════════════════════════════════════════════════════════════════
# Intake modal submission
# ══════════════════════════════════════════════════════════════════════════

def handle_intake_submission(ack, body: dict, client: WebClient) -> None:
    """
    Called when a user submits the /decision new modal.

    1. Validate inputs (return errors to Slack if invalid).
    2. Acknowledge immediately so the modal closes.
    3. Kick off background processing (Airtable + LLM) in a daemon thread.
    """
    values = body["view"]["state"]["values"]
    user_id: str = body["user"]["id"]

    # ── Extract field values ───────────────────────────────────────────
    title = _val(values, BID_TITLE, AID_TITLE)
    decision_type = _sel(values, BID_TYPE, AID_TYPE)
    sponsor_id = _user(values, BID_SPONSOR, AID_SPONSOR)
    decision_maker_id = _user(values, BID_DECISION_MAKER, AID_DECISION_MAKER)
    context_user = _val(values, BID_CONTEXT, AID_CONTEXT)
    links = _val(values, BID_LINKS, AID_LINKS) or ""
    visibility = _radio(values, BID_VISIBILITY, AID_VISIBILITY) or "Public"

    # ── Inline validation ──────────────────────────────────────────────
    errors: dict[str, str] = {}
    if not title or len(title.strip()) < 5:
        errors[BID_TITLE] = "Please provide a more descriptive title (at least 5 characters)."
    if not context_user or len(context_user.strip()) < 20:
        errors[BID_CONTEXT] = "Please provide at least 20 characters of context."

    if errors:
        ack(response_action="errors", errors=errors)
        return

    ack()  # Close the modal immediately — heavy work happens below in a thread

    # ── Background processing ──────────────────────────────────────────
    payload = {
        "title": title.strip(),
        "decision_type": decision_type,
        "sponsor_id": sponsor_id,
        "decision_maker_id": decision_maker_id,
        "context_user": context_user.strip(),
        "links": links.strip(),
        "visibility": visibility,
        "requester_id": user_id,
        "priority": _PRIORITY_MAP.get(decision_type, "P2"),
    }

    thread = threading.Thread(
        target=_process_intake,
        args=(payload, client),
        daemon=True,
    )
    thread.start()


def _process_intake(payload: dict[str, Any], client: WebClient) -> None:
    """
    Background task executed after modal is acknowledged.

    Steps:
      1. Create Airtable record (DRAFTING)
      2. Post root message to #ics-decisions (if Public)
      3. Store thread_ts on the record
      4. Call LLM to generate draft
      5. Update Airtable with AI draft → advance to HITL_REVIEW
      6. DM HITL reviewer with draft + action buttons
    """
    title = payload["title"]
    try:
        # ── 1. Create Airtable record ──────────────────────────────────
        record = at.create_decision(
            title=title,
            decision_type=payload["decision_type"],
            requester_slack_id=payload["requester_id"],
            sponsor_slack_id=payload["sponsor_id"],
            hitl_reviewer_slack_id=config.HITL_REVIEWER_SLACK_ID,
            context_user=payload["context_user"],
            visibility=payload["visibility"],
            priority=payload["priority"],
        )
        record_id: str = record["id"]
        fields: dict = record["fields"]
        sla_deadline_str: str = fields.get(F_SLA_DEADLINE, "N/A")
        draft_due_str: str = fields.get(F_DRAFT_DUE, "N/A")

        logger.info("Created record %s for '%s'", record_id, title)

        # Append links to context if provided
        if payload["links"]:
            at.update_decision(
                record_id,
                {at.F_CONTEXT_USER: payload["context_user"] + "\n\nLinks:\n" + payload["links"]},
            )

        # Store Decision Maker on the record
        at.update_decision(record_id, {at.F_DECISION_MAKER: payload["decision_maker_id"]})

        # ── 2. Post root message to channel ───────────────────────────
        thread_ts: str | None = None
        if payload["visibility"] == "Public":
            blocks = build_intake_channel_message(
                record_id=record_id,
                title=title,
                decision_type=payload["decision_type"],
                priority=payload["priority"],
                requester_id=payload["requester_id"],
                sponsor_id=payload["sponsor_id"],
                decision_maker_id=payload["decision_maker_id"],
                visibility=payload["visibility"],
                sla_deadline_str=sla_deadline_str,
            )
            try:
                resp = client.chat_postMessage(
                    channel=config.DECISIONS_CHANNEL,
                    text=f"New decision submitted: {title}",
                    blocks=blocks,
                )
                thread_ts = resp["ts"]
            except Exception as exc:
                logger.error("Failed to post to channel: %s", exc)

        # ── 3. Store thread_ts ─────────────────────────────────────────
        if thread_ts:
            at.set_thread_ts(record_id, thread_ts)

        # ── 4. Generate LLM draft ──────────────────────────────────────
        draft = generate_decision_draft(
            title=title,
            decision_type=payload["decision_type"],
            context_user=payload["context_user"],
            sponsor_slack_id=payload["sponsor_id"],
            priority=payload["priority"],
        )

        # ── 5. Update Airtable → HITL_REVIEW ──────────────────────────
        at.set_ai_draft(
            record_id,
            context_ai=draft["context_ai"],
            recommendation_ai=draft["recommendation_ai"],
            options_ai=draft["options_ai"],
        )
        logger.info("Record %s advanced to HITL_REVIEW", record_id)

        # ── 6. DM HITL reviewer ────────────────────────────────────────
        dm_blocks = build_hitl_dm_message(
            record_id=record_id,
            title=title,
            decision_type=payload["decision_type"],
            priority=payload["priority"],
            requester_id=payload["requester_id"],
            context_user=payload["context_user"],
            context_ai=draft["context_ai"],
            recommendation_ai=draft["recommendation_ai"],
            options_ai=draft["options_ai"],
            draft_due_str=draft_due_str,
        )
        try:
            client.chat_postMessage(
                channel=config.HITL_REVIEWER_SLACK_ID,
                text=f"Decision for HITL review: {title}",
                blocks=dm_blocks,
            )
            logger.info("DM sent to HITL reviewer %s", config.HITL_REVIEWER_SLACK_ID)
        except Exception as exc:
            logger.error("Failed to DM HITL reviewer: %s", exc)

        # Notify requester that submission was received
        try:
            client.chat_postMessage(
                channel=payload["requester_id"],
                text=(
                    f":white_check_mark: Your decision request *{title}* has been submitted "
                    f"and is now in HITL review. SLA deadline: {sla_deadline_str}."
                ),
            )
        except Exception as exc:
            logger.warning("Could not DM requester: %s", exc)

    except Exception as exc:
        logger.error("_process_intake failed for '%s': %s", title, exc, exc_info=True)
        # Best-effort notification to requester
        try:
            client.chat_postMessage(
                channel=payload["requester_id"],
                text=(
                    f":warning: Something went wrong processing your decision request *{title}*. "
                    "Please contact the ICS ops team."
                ),
            )
        except Exception:
            pass


# ══════════════════════════════════════════════════════════════════════════
# Resolution modal submission  (Make Decision)
# ══════════════════════════════════════════════════════════════════════════

def handle_resolution_submission(ack, body: dict, client: WebClient) -> None:
    """
    Called when the Decision Maker submits the resolution modal.
    Closes the decision in Airtable and posts a summary to the thread.
    """
    ack()

    values = body["view"]["state"]["values"]
    user_id: str = body["user"]["id"]
    record_id: str = body["view"]["private_metadata"]

    outcome = _val(values, BID_OUTCOME, AID_OUTCOME) or ""
    rationale = _val(values, BID_RATIONALE, AID_RATIONALE) or ""

    thread = threading.Thread(
        target=_process_resolution,
        args=(record_id, outcome, rationale, user_id, client),
        daemon=True,
    )
    thread.start()


def _process_resolution(
    record_id: str,
    outcome: str,
    rationale: str,
    decision_maker_id: str,
    client: WebClient,
) -> None:
    try:
        # Update Airtable → CLOSED
        updated = at.close_decision(
            record_id,
            outcome=outcome,
            rationale=rationale,
            decision_maker_slack_id=decision_maker_id,
        )
        if not updated:
            logger.error("close_decision returned None for %s", record_id)
            return

        logger.info("Record %s CLOSED by %s", record_id, decision_maker_id)

        # Post summary to the Slack thread (if one exists)
        thread_ts = updated["fields"].get(at.F_SLACK_THREAD_TS)
        title = updated["fields"].get(at.F_TITLE, "Decision")
        blocks = build_closed_thread_message(
            outcome=outcome,
            rationale=rationale,
            decision_maker_id=decision_maker_id,
        )

        if thread_ts and config.DECISIONS_CHANNEL:
            try:
                client.chat_postMessage(
                    channel=config.DECISIONS_CHANNEL,
                    thread_ts=thread_ts,
                    text=f"Decision closed: {outcome}",
                    blocks=blocks,
                )
            except Exception as exc:
                logger.error("Failed to post resolution to thread: %s", exc)

        # DM the requester and sponsor
        for slack_id_field in (at.F_REQUESTER, at.F_SPONSOR):
            uid = updated["fields"].get(slack_id_field)
            if uid and uid != decision_maker_id:
                try:
                    client.chat_postMessage(
                        channel=uid,
                        text=f":white_check_mark: Decision *{title}* has been closed. Outcome: {outcome}",
                    )
                except Exception as exc:
                    logger.warning("Could not DM %s: %s", uid, exc)

    except Exception as exc:
        logger.error("_process_resolution failed for %s: %s", record_id, exc, exc_info=True)


# ── Value extraction helpers ───────────────────────────────────────────────

def _val(values: dict, block_id: str, action_id: str) -> str | None:
    """Extract a plain_text_input value."""
    return (
        values.get(block_id, {})
        .get(action_id, {})
        .get("value")
    )


def _sel(values: dict, block_id: str, action_id: str) -> str | None:
    """Extract a static_select value."""
    opt = (
        values.get(block_id, {})
        .get(action_id, {})
        .get("selected_option")
    )
    return opt["value"] if opt else None


def _user(values: dict, block_id: str, action_id: str) -> str | None:
    """Extract a users_select value."""
    return (
        values.get(block_id, {})
        .get(action_id, {})
        .get("selected_user")
    )


def _radio(values: dict, block_id: str, action_id: str) -> str | None:
    """Extract a radio_buttons value."""
    opt = (
        values.get(block_id, {})
        .get(action_id, {})
        .get("selected_option")
    )
    return opt["value"] if opt else None
