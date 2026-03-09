"""
Airtable CRUD helpers for the "Decisions" table.

All field names mirror the spec exactly. Callers work with plain dicts;
this module handles serialisation, retries, and mapping to pyairtable's API.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from pyairtable import Api
from pyairtable.formulas import match

import config
from utils.business_days import add_business_days, format_iso, now_la

logger = logging.getLogger(__name__)

# ── Airtable field name constants ──────────────────────────────────────────
# Keeps callers DRY and prevents typos.
F_DECISION_ID = "Decision ID"
F_STATUS = "Status"
F_VISIBILITY = "Visibility"
F_TITLE = "Decision Title"
F_TYPE = "Decision Type"
F_PRIORITY = "Priority"
F_REQUESTER = "Requester Slack ID"
F_SPONSOR = "Sponsor Slack ID"
F_DECISION_MAKER = "Decision Maker Slack ID"
F_HITL_REVIEWER = "HITL Reviewer Slack ID"
F_DATE_SUBMITTED = "Date Submitted"
F_DRAFT_DUE = "Draft Due"
F_SLA_DEADLINE = "SLA Deadline"
F_CONTEXT_USER = "Context Summary (User)"
F_CONTEXT_AI = "Context Summary (AI)"
F_RECOMMENDATION_AI = "Recommendation (AI)"
F_OPTIONS_AI = "Options (AI)"
F_OUTCOME = "Outcome"
F_RATIONALE = "Rationale"
F_SLACK_THREAD_TS = "Slack Thread TS"
F_NUDGES_SENT = "Nudges Sent"

# ── Status values (state machine) ─────────────────────────────────────────
class Status:
    INTAKE_RECEIVED = "INTAKE_RECEIVED"
    DRAFTING = "DRAFTING"
    HITL_REVIEW = "HITL_REVIEW"
    PENDING_DECISION = "PENDING_DECISION"
    CLOSED = "CLOSED"
    ESCALATED = "ESCALATED"
    CANCELED = "CANCELED"


def _get_table():
    """Return a pyairtable Table object. Called lazily so tests can mock config."""
    api = Api(config.AIRTABLE_API_KEY)
    return api.table(config.AIRTABLE_BASE_ID, config.AIRTABLE_TABLE_NAME)


# ── Create ─────────────────────────────────────────────────────────────────

def create_decision(
    *,
    title: str,
    decision_type: str,
    requester_slack_id: str,
    sponsor_slack_id: str,
    hitl_reviewer_slack_id: str,
    context_user: str,
    visibility: str = "Public",
    priority: str = "P1",
) -> dict[str, Any]:
    """
    Insert a new record in the DRAFTING state.
    Returns the full Airtable record dict (fields + id + createdTime).
    """
    submitted_at = now_la()
    draft_due = add_business_days(submitted_at, 2)
    sla_deadline = add_business_days(submitted_at, 4)

    fields = {
        F_STATUS: Status.DRAFTING,
        F_VISIBILITY: visibility,
        F_TITLE: title,
        F_TYPE: decision_type,
        F_PRIORITY: priority,
        F_REQUESTER: requester_slack_id,
        F_SPONSOR: sponsor_slack_id,
        F_HITL_REVIEWER: hitl_reviewer_slack_id,
        F_DATE_SUBMITTED: format_iso(submitted_at),
        F_DRAFT_DUE: format_iso(draft_due),
        F_SLA_DEADLINE: format_iso(sla_deadline),
        F_CONTEXT_USER: context_user,
        F_NUDGES_SENT: json.dumps({}),
    }

    try:
        table = _get_table()
        record = table.create(fields)
        logger.info("Created Airtable record %s for '%s'", record["id"], title)
        return record
    except Exception as exc:
        logger.error("Airtable create_decision failed: %s", exc, exc_info=True)
        raise


# ── Read ───────────────────────────────────────────────────────────────────

def get_decision_by_record_id(record_id: str) -> dict[str, Any] | None:
    """Fetch a single record by Airtable record ID (recXXX)."""
    try:
        table = _get_table()
        return table.get(record_id)
    except Exception as exc:
        logger.error("get_decision_by_record_id(%s) failed: %s", record_id, exc)
        return None


def get_decisions_by_status(*statuses: str) -> list[dict[str, Any]]:
    """Return all records whose Status matches any of the given values."""
    if not statuses:
        return []

    # Build an OR formula: OR({Status}='A', {Status}='B', ...)
    clauses = [f"{{Status}}='{s}'" for s in statuses]
    formula = f"OR({', '.join(clauses)})" if len(clauses) > 1 else clauses[0]

    try:
        table = _get_table()
        return table.all(formula=formula)
    except Exception as exc:
        logger.error("get_decisions_by_status failed: %s", exc, exc_info=True)
        return []


def get_decision_by_thread_ts(thread_ts: str) -> dict[str, Any] | None:
    """Lookup a record by Slack thread timestamp (used for event deduplication)."""
    try:
        table = _get_table()
        formula = match({F_SLACK_THREAD_TS: thread_ts})
        results = table.all(formula=formula)
        return results[0] if results else None
    except Exception as exc:
        logger.error("get_decision_by_thread_ts(%s) failed: %s", thread_ts, exc)
        return None


# ── Update ─────────────────────────────────────────────────────────────────

def update_decision(record_id: str, fields: dict[str, Any]) -> dict[str, Any] | None:
    """Partial update — only the supplied fields are changed."""
    try:
        table = _get_table()
        updated = table.update(record_id, fields)
        logger.info("Updated record %s: %s", record_id, list(fields.keys()))
        return updated
    except Exception as exc:
        logger.error("update_decision(%s) failed: %s", record_id, exc, exc_info=True)
        return None


def set_status(record_id: str, new_status: str) -> dict[str, Any] | None:
    """Convenience wrapper to transition a record's Status field."""
    return update_decision(record_id, {F_STATUS: new_status})


def set_ai_draft(
    record_id: str,
    *,
    context_ai: str,
    recommendation_ai: str,
    options_ai: str,
) -> dict[str, Any] | None:
    """Store the LLM-generated draft fields and advance to HITL_REVIEW."""
    return update_decision(
        record_id,
        {
            F_CONTEXT_AI: context_ai,
            F_RECOMMENDATION_AI: recommendation_ai,
            F_OPTIONS_AI: options_ai,
            F_STATUS: Status.HITL_REVIEW,
        },
    )


def set_thread_ts(record_id: str, thread_ts: str) -> dict[str, Any] | None:
    return update_decision(record_id, {F_SLACK_THREAD_TS: thread_ts})


def record_nudge(record_id: str, nudge_key: str) -> bool:
    """
    Mark a nudge as sent (idempotent).
    `nudge_key` is a string like 'draft_overdue_day1' or 'sla_overdue'.
    Returns True if the nudge was newly recorded, False if already sent.
    """
    record = get_decision_by_record_id(record_id)
    if not record:
        return False

    raw = record["fields"].get(F_NUDGES_SENT) or "{}"
    try:
        nudges: dict = json.loads(raw)
    except json.JSONDecodeError:
        nudges = {}

    if nudges.get(nudge_key):
        return False  # already sent

    nudges[nudge_key] = True
    update_decision(record_id, {F_NUDGES_SENT: json.dumps(nudges)})
    return True


def close_decision(
    record_id: str,
    *,
    outcome: str,
    rationale: str,
    decision_maker_slack_id: str,
) -> dict[str, Any] | None:
    """Record the final outcome and close the decision."""
    return update_decision(
        record_id,
        {
            F_STATUS: Status.CLOSED,
            F_OUTCOME: outcome,
            F_RATIONALE: rationale,
            F_DECISION_MAKER: decision_maker_slack_id,
        },
    )
