"""
Interactive component action handlers.

Registered in app.py:
    bolt_app.action("hitl_approve")(handle_hitl_approve)
    bolt_app.action("hitl_request_info")(handle_hitl_request_info)
    bolt_app.action("hitl_edit_draft")(handle_hitl_edit_draft)
    bolt_app.action("make_decision")(handle_make_decision)
    bolt_app.view(EDIT_DRAFT_MODAL_ID)(handle_edit_draft_submission)
"""
from __future__ import annotations

import logging
import threading
from typing import Any

from slack_sdk import WebClient

import config
from utils import airtable_client as at
from utils.llm import AIDraft
from utils.slack_ui import (
    build_pending_decision_dm_message,
    build_resolution_modal,
    EDIT_DRAFT_MODAL_ID,
    BID_CONTEXT_AI, AID_CONTEXT_AI,
    BID_RECOMMENDATION_AI, AID_RECOMMENDATION_AI,
    BID_OPTIONS_AI, AID_OPTIONS_AI,
    build_edit_draft_modal,
)

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════════
# HITL: Approve & Route
# ══════════════════════════════════════════════════════════════════════════

def handle_hitl_approve(ack, body: dict, client: WebClient) -> None:
    """
    HITL reviewer approves the AI draft.
    Status: HITL_REVIEW → PENDING_DECISION.
    Routes to Decision Maker + Sponsor via DM.
    """
    ack()

    record_id: str = body["actions"][0]["value"]
    reviewer_id: str = body["user"]["id"]
    msg_ts: str | None = _msg_ts(body)
    msg_channel: str | None = _msg_channel(body)

    thread = threading.Thread(
        target=_process_approve,
        args=(record_id, reviewer_id, msg_ts, msg_channel, client),
        daemon=True,
    )
    thread.start()


def _process_approve(
    record_id: str,
    reviewer_id: str,
    msg_ts: str | None,
    msg_channel: str | None,
    client: WebClient,
) -> None:
    record = at.get_decision_by_record_id(record_id)
    if not record:
        logger.error("hitl_approve: record %s not found", record_id)
        return

    fields = record["fields"]
    title = fields.get(at.F_TITLE, "Untitled")

    # ── Advance status ─────────────────────────────────────────────────
    at.set_status(record_id, at.Status.PENDING_DECISION)
    logger.info("Record %s → PENDING_DECISION (approved by %s)", record_id, reviewer_id)

    # ── DM Decision Maker ──────────────────────────────────────────────
    decision_maker_id = fields.get(at.F_DECISION_MAKER)
    sponsor_id = fields.get(at.F_SPONSOR)
    sla_deadline_str = fields.get(at.F_SLA_DEADLINE, "N/A")
    context_ai = fields.get(at.F_CONTEXT_AI, "")
    recommendation_ai = fields.get(at.F_RECOMMENDATION_AI, "")
    options_ai = fields.get(at.F_OPTIONS_AI, "")

    dm_blocks = build_pending_decision_dm_message(
        record_id=record_id,
        title=title,
        context_ai=context_ai,
        recommendation_ai=recommendation_ai,
        options_ai=options_ai,
        sla_deadline_str=sla_deadline_str,
    )

    for uid in _unique(decision_maker_id, sponsor_id):
        try:
            client.chat_postMessage(
                channel=uid,
                text=f"Decision ready for your input: {title}",
                blocks=dm_blocks,
            )
            logger.info("Routed decision %s to %s", record_id, uid)
        except Exception as exc:
            logger.error("Failed to DM %s: %s", uid, exc)

    # ── Replace HITL DM buttons with confirmation ──────────────────────
    if msg_ts and msg_channel:
        _replace_buttons_with_status(
            client,
            channel=msg_channel,
            ts=msg_ts,
            status_text=f":white_check_mark: Approved & routed to <@{decision_maker_id}> — {title}",
        )


# ══════════════════════════════════════════════════════════════════════════
# HITL: Request More Info
# ══════════════════════════════════════════════════════════════════════════

def handle_hitl_request_info(ack, body: dict, client: WebClient) -> None:
    """
    HITL reviewer asks the requester for more context.
    Status stays HITL_REVIEW; reviewer's DM buttons remain active.
    """
    ack()

    record_id: str = body["actions"][0]["value"]
    reviewer_id: str = body["user"]["id"]

    thread = threading.Thread(
        target=_process_request_info,
        args=(record_id, reviewer_id, client),
        daemon=True,
    )
    thread.start()


def _process_request_info(
    record_id: str,
    reviewer_id: str,
    client: WebClient,
) -> None:
    record = at.get_decision_by_record_id(record_id)
    if not record:
        return

    fields = record["fields"]
    requester_id = fields.get(at.F_REQUESTER)
    title = fields.get(at.F_TITLE, "Untitled")

    if requester_id:
        try:
            client.chat_postMessage(
                channel=requester_id,
                text=(
                    f":information_source: The HITL reviewer for *{title}* "
                    f"(<@{reviewer_id}>) has requested more information. "
                    "Please reply here or update the decision context directly."
                ),
            )
        except Exception as exc:
            logger.error("Failed to DM requester for more info: %s", exc)

    # Acknowledge to reviewer
    try:
        client.chat_postMessage(
            channel=reviewer_id,
            text=f":speech_balloon: More-info request sent to <@{requester_id}> for *{title}*.",
        )
    except Exception as exc:
        logger.warning("Could not confirm to reviewer: %s", exc)


# ══════════════════════════════════════════════════════════════════════════
# HITL: Edit Draft
# ══════════════════════════════════════════════════════════════════════════

def handle_hitl_edit_draft(ack, body: dict, client: WebClient) -> None:
    """
    Open a modal pre-populated with the current AI draft fields for editing.
    """
    ack()

    record_id: str = body["actions"][0]["value"]
    trigger_id: str = body["trigger_id"]

    record = at.get_decision_by_record_id(record_id)
    if not record:
        logger.error("hitl_edit_draft: record %s not found", record_id)
        return

    fields = record["fields"]
    try:
        client.views_open(
            trigger_id=trigger_id,
            view=build_edit_draft_modal(
                record_id=record_id,
                context_ai=fields.get(at.F_CONTEXT_AI, ""),
                recommendation_ai=fields.get(at.F_RECOMMENDATION_AI, ""),
                options_ai=fields.get(at.F_OPTIONS_AI, ""),
            ),
        )
    except Exception as exc:
        logger.error("Failed to open edit_draft modal: %s", exc, exc_info=True)


def handle_edit_draft_submission(ack, body: dict, client: WebClient) -> None:
    """
    Processes the Edit Draft modal submission.
    Updates Airtable AI fields; status stays HITL_REVIEW.
    """
    ack()

    values = body["view"]["state"]["values"]
    record_id: str = body["view"]["private_metadata"]
    editor_id: str = body["user"]["id"]

    context_ai = _val(values, BID_CONTEXT_AI, AID_CONTEXT_AI) or ""
    recommendation_ai = _val(values, BID_RECOMMENDATION_AI, AID_RECOMMENDATION_AI) or ""
    options_ai = _val(values, BID_OPTIONS_AI, AID_OPTIONS_AI) or ""

    thread = threading.Thread(
        target=_process_edit_draft,
        args=(record_id, context_ai, recommendation_ai, options_ai, editor_id, client),
        daemon=True,
    )
    thread.start()


def _process_edit_draft(
    record_id: str,
    context_ai: str,
    recommendation_ai: str,
    options_ai: str,
    editor_id: str,
    client: WebClient,
) -> None:
    updated = at.update_decision(
        record_id,
        {
            at.F_CONTEXT_AI: context_ai,
            at.F_RECOMMENDATION_AI: recommendation_ai,
            at.F_OPTIONS_AI: options_ai,
        },
    )
    if updated:
        logger.info("Draft edited on record %s by %s", record_id, editor_id)
        title = updated["fields"].get(at.F_TITLE, "Untitled")
        try:
            client.chat_postMessage(
                channel=editor_id,
                text=f":pencil2: Draft for *{title}* updated. You can now approve and route it.",
            )
        except Exception as exc:
            logger.warning("Could not confirm edit to reviewer: %s", exc)


# ══════════════════════════════════════════════════════════════════════════
# Make Decision  (opens resolution modal — submission handled in modals.py)
# ══════════════════════════════════════════════════════════════════════════

def handle_make_decision(ack, body: dict, client: WebClient) -> None:
    """
    Decision Maker clicks [Make Decision] → open the resolution modal.
    """
    ack()

    record_id: str = body["actions"][0]["value"]
    trigger_id: str = body["trigger_id"]

    try:
        client.views_open(
            trigger_id=trigger_id,
            view=build_resolution_modal(record_id),
        )
        logger.info("Opened resolution modal for record %s", record_id)
    except Exception as exc:
        logger.error("Failed to open resolution modal: %s", exc, exc_info=True)


# ── Private helpers ────────────────────────────────────────────────────────

def _replace_buttons_with_status(
    client: WebClient,
    *,
    channel: str,
    ts: str,
    status_text: str,
) -> None:
    """Replace the action buttons in a DM with a plain status line."""
    try:
        client.chat_update(
            channel=channel,
            ts=ts,
            text=status_text,
            blocks=[
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": status_text},
                }
            ],
        )
    except Exception as exc:
        logger.warning("Could not update button message: %s", exc)


def _msg_ts(body: dict) -> str | None:
    return body.get("message", {}).get("ts")


def _msg_channel(body: dict) -> str | None:
    ch = body.get("channel") or {}
    return ch.get("id") if isinstance(ch, dict) else None


def _unique(*ids: str | None) -> list[str]:
    """Return deduplicated non-None IDs preserving order."""
    seen: set[str] = set()
    result: list[str] = []
    for uid in ids:
        if uid and uid not in seen:
            seen.add(uid)
            result.append(uid)
    return result


def _val(values: dict, block_id: str, action_id: str) -> str | None:
    return (
        values.get(block_id, {})
        .get(action_id, {})
        .get("value")
    )
