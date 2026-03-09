"""
SLA check engine — called by the /internal/run_sla_checks FastAPI endpoint.

Nudge keys stored in Airtable "Nudges Sent" (JSON):
  "draft_overdue"      — Draft Due has passed while still in DRAFTING or HITL_REVIEW
  "sla_day3_nudge"     — 1 business day before SLA deadline (day 3 of 4)
  "sla_overdue"        — SLA Deadline has passed (first notice)
  "escalated"          — Record formally moved to ESCALATED status

All nudges are idempotent: record_nudge() returns False if already sent.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any

from slack_sdk import WebClient

import config
from utils import airtable_client as at
from utils.business_days import is_past_due, business_days_between, now_la

logger = logging.getLogger(__name__)

# Statuses that are still "open" and subject to SLA monitoring
_OPEN_STATUSES = (
    at.Status.DRAFTING,
    at.Status.HITL_REVIEW,
    at.Status.PENDING_DECISION,
    at.Status.INTAKE_RECEIVED,
)


def run_sla_checks(client: WebClient) -> int:
    """
    Scan all open Airtable records and send nudges / escalations as needed.
    Returns the total number of new nudges sent.
    """
    records = at.get_decisions_by_status(*_OPEN_STATUSES)
    logger.info("SLA check: found %d open records", len(records))

    total_nudges = 0
    for record in records:
        try:
            total_nudges += _check_record(record, client)
        except Exception as exc:
            logger.error(
                "SLA check failed for record %s: %s",
                record.get("id"),
                exc,
                exc_info=True,
            )

    logger.info("SLA check complete: %d new nudges sent", total_nudges)
    return total_nudges


# ── Per-record logic ───────────────────────────────────────────────────────

def _check_record(record: dict[str, Any], client: WebClient) -> int:
    """Evaluate a single record against all SLA rules. Returns nudges sent."""
    fields = record["fields"]
    record_id = record["id"]
    status = fields.get(at.F_STATUS, "")
    title = fields.get(at.F_TITLE, "Untitled")
    nudges_sent = 0

    draft_due_raw = fields.get(at.F_DRAFT_DUE)
    sla_deadline_raw = fields.get(at.F_SLA_DEADLINE)

    draft_due = _parse_dt(draft_due_raw)
    sla_deadline = _parse_dt(sla_deadline_raw)
    now = now_la()

    # ── Rule 1: Draft overdue ──────────────────────────────────────────
    # Fires when Draft Due has passed and the record is still pre-PENDING
    if (
        draft_due
        and is_past_due(draft_due)
        and status in (at.Status.DRAFTING, at.Status.HITL_REVIEW, at.Status.INTAKE_RECEIVED)
    ):
        if at.record_nudge(record_id, "draft_overdue"):
            nudges_sent += 1
            _send_draft_overdue_nudge(client, record_id, fields, title, sla_deadline_raw or "N/A")

    # ── Rule 2: Day-3 early warning (1 BD before SLA deadline) ────────
    # Fires when <= 1 business day remains before the SLA deadline
    if sla_deadline and not is_past_due(sla_deadline):
        bdays_left = business_days_between(now, sla_deadline)
        if bdays_left <= 1 and status == at.Status.PENDING_DECISION:
            if at.record_nudge(record_id, "sla_day3_nudge"):
                nudges_sent += 1
                _send_day3_nudge(client, record_id, fields, title, sla_deadline_raw or "N/A")

    # ── Rule 3: SLA overdue — first notice ────────────────────────────
    if sla_deadline and is_past_due(sla_deadline):
        if at.record_nudge(record_id, "sla_overdue"):
            nudges_sent += 1
            _send_sla_overdue_nudge(client, record_id, fields, title)

    # ── Rule 4: Escalate — only after sla_overdue has already fired ───
    # This prevents a same-run double-fire: escalation is always a second pass.
    nudges_raw = fields.get(at.F_NUDGES_SENT) or "{}"
    try:
        nudges_flags: dict = json.loads(nudges_raw)
    except json.JSONDecodeError:
        nudges_flags = {}

    if (
        sla_deadline
        and is_past_due(sla_deadline)
        and nudges_flags.get("sla_overdue")          # already notified once
        and not nudges_flags.get("escalated")         # not yet escalated
        and status not in (at.Status.ESCALATED, at.Status.CLOSED, at.Status.CANCELED)
    ):
        if at.record_nudge(record_id, "escalated"):
            nudges_sent += 1
            at.set_status(record_id, at.Status.ESCALATED)
            _send_escalation_notice(client, record_id, fields, title)

    return nudges_sent


# ── Nudge message senders ──────────────────────────────────────────────────

def _send_draft_overdue_nudge(
    client: WebClient,
    record_id: str,
    fields: dict,
    title: str,
    sla_deadline_str: str,
) -> None:
    """Nudge the HITL reviewer when the draft window has passed."""
    hitl_id = fields.get(at.F_HITL_REVIEWER) or config.HITL_REVIEWER_SLACK_ID
    requester_id = fields.get(at.F_REQUESTER, "")
    msg = (
        f":warning: *Draft overdue* — `{title}`\n\n"
        f"The 2-business-day draft window has passed. "
        f"Please review and approve this decision.\n"
        f"*Requester:* <@{requester_id}>\n"
        f"*SLA Deadline:* {sla_deadline_str}\n"
        f"*Record ID:* `{record_id}`"
    )
    _dm(client, hitl_id, msg)
    logger.info("Draft overdue nudge sent for %s → %s", record_id, hitl_id)


def _send_day3_nudge(
    client: WebClient,
    record_id: str,
    fields: dict,
    title: str,
    sla_deadline_str: str,
) -> None:
    """Nudge the Decision Maker and Sponsor with 1 business day remaining."""
    decision_maker_id = fields.get(at.F_DECISION_MAKER)
    sponsor_id = fields.get(at.F_SPONSOR)
    msg = (
        f":hourglass: *Decision needed soon* — `{title}`\n\n"
        f"The SLA deadline is approaching (*{sla_deadline_str}*). "
        f"Please record your decision to avoid escalation.\n"
        f"*Record ID:* `{record_id}`"
    )
    for uid in _unique(decision_maker_id, sponsor_id):
        _dm(client, uid, msg)
    logger.info("Day-3 nudge sent for %s", record_id)


def _send_sla_overdue_nudge(
    client: WebClient,
    record_id: str,
    fields: dict,
    title: str,
) -> None:
    """Notify all parties that the SLA deadline has been missed."""
    decision_maker_id = fields.get(at.F_DECISION_MAKER)
    sponsor_id = fields.get(at.F_SPONSOR)
    hitl_id = fields.get(at.F_HITL_REVIEWER) or config.HITL_REVIEWER_SLACK_ID
    requester_id = fields.get(at.F_REQUESTER)

    msg = (
        f":red_circle: *SLA Overdue* — `{title}`\n\n"
        f"This decision has exceeded its 4-business-day SLA. "
        f"If not resolved, it will be escalated.\n"
        f"*Record ID:* `{record_id}`"
    )
    for uid in _unique(decision_maker_id, sponsor_id, hitl_id, requester_id):
        _dm(client, uid, msg)
    logger.info("SLA overdue nudge sent for %s", record_id)


def _send_escalation_notice(
    client: WebClient,
    record_id: str,
    fields: dict,
    title: str,
) -> None:
    """Post escalation notice to #ics-decisions channel and DM all parties."""
    decision_maker_id = fields.get(at.F_DECISION_MAKER)
    sponsor_id = fields.get(at.F_SPONSOR)
    hitl_id = fields.get(at.F_HITL_REVIEWER) or config.HITL_REVIEWER_SLACK_ID
    requester_id = fields.get(at.F_REQUESTER)
    thread_ts = fields.get(at.F_SLACK_THREAD_TS)

    channel_msg = (
        f":rotating_light: *ESCALATED* — `{title}`\n\n"
        f"This decision has been escalated due to an unmet SLA. "
        f"Immediate attention required.\n"
        f"*Decision Maker:* <@{decision_maker_id}>\n"
        f"*Sponsor:* <@{sponsor_id}>\n"
        f"*Record ID:* `{record_id}`"
    )

    # Post to #ics-decisions (in thread if possible)
    try:
        kwargs: dict = {
            "channel": config.DECISIONS_CHANNEL,
            "text": channel_msg,
        }
        if thread_ts:
            kwargs["thread_ts"] = thread_ts
        client.chat_postMessage(**kwargs)
    except Exception as exc:
        logger.error("Failed to post escalation to channel: %s", exc)

    dm_msg = (
        f":rotating_light: *Decision ESCALATED* — `{title}`\n\n"
        f"This decision was escalated because the SLA was not met. "
        f"Please take action immediately.\n"
        f"*Record ID:* `{record_id}`"
    )
    for uid in _unique(decision_maker_id, sponsor_id, hitl_id, requester_id):
        _dm(client, uid, dm_msg)

    logger.info("Escalation notice sent for %s", record_id)


# ── Helpers ────────────────────────────────────────────────────────────────

def _dm(client: WebClient, user_id: str | None, text: str) -> None:
    if not user_id:
        return
    try:
        client.chat_postMessage(channel=user_id, text=text)
    except Exception as exc:
        logger.warning("Could not DM %s: %s", user_id, exc)


def _parse_dt(raw: str | None) -> datetime | None:
    """Parse an ISO-8601 string from Airtable into an aware datetime."""
    if not raw:
        return None
    try:
        # Python 3.11+ handles Z; fromisoformat on 3.10 needs manual replace
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        logger.warning("Could not parse datetime: %r", raw)
        return None


def _unique(*ids: str | None) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for uid in ids:
        if uid and uid not in seen:
            seen.add(uid)
            result.append(uid)
    return result
