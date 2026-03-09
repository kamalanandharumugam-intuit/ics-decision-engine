"""
Block Kit builders for every Slack surface used by the Decision Tool.

Keeping all UI definitions here (not scattered across handlers) makes it
easy to iterate on copy/layout without touching business logic.
"""
from __future__ import annotations

from typing import Any

# ── Modal callback IDs ─────────────────────────────────────────────────────
INTAKE_MODAL_ID = "decision_intake_modal"
RESOLUTION_MODAL_ID = "decision_resolution_modal"
EDIT_DRAFT_MODAL_ID = "hitl_edit_draft_modal"

# ── Block / Action IDs for the edit-draft modal ────────────────────────────
BID_CONTEXT_AI = "context_ai_block"
AID_CONTEXT_AI = "context_ai_input"

BID_RECOMMENDATION_AI = "recommendation_ai_block"
AID_RECOMMENDATION_AI = "recommendation_ai_input"

BID_OPTIONS_AI = "options_ai_block"
AID_OPTIONS_AI = "options_ai_input"

# ── Block / Action IDs for the intake modal ────────────────────────────────
BID_TITLE = "title_block"
AID_TITLE = "title_input"

BID_TYPE = "type_block"
AID_TYPE = "type_select"

BID_SPONSOR = "sponsor_block"
AID_SPONSOR = "sponsor_select"

BID_DECISION_MAKER = "decision_maker_block"
AID_DECISION_MAKER = "decision_maker_select"

BID_CONTEXT = "context_block"
AID_CONTEXT = "context_input"

BID_LINKS = "links_block"
AID_LINKS = "links_input"

BID_VISIBILITY = "visibility_block"
AID_VISIBILITY = "visibility_radio"

# ── Block / Action IDs for the resolution modal ────────────────────────────
BID_OUTCOME = "outcome_block"
AID_OUTCOME = "outcome_input"

BID_RATIONALE = "rationale_block"
AID_RATIONALE = "rationale_input"


# ══════════════════════════════════════════════════════════════════════════
# Intake Modal
# ══════════════════════════════════════════════════════════════════════════

def build_intake_modal(trigger_id: str | None = None) -> dict[str, Any]:
    """
    Returns the Block Kit view payload for the /decision new intake modal.
    `trigger_id` is unused here (passed to client.views_open separately)
    but kept as a convenience reminder for callers.
    """
    return {
        "type": "modal",
        "callback_id": INTAKE_MODAL_ID,
        "title": {"type": "plain_text", "text": "New Decision Request"},
        "submit": {"type": "plain_text", "text": "Submit"},
        "close": {"type": "plain_text", "text": "Cancel"},
        "blocks": [
            # ── Header context ─────────────────────────────────────────
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": (
                            ":brain: An AI draft will be generated after submission. "
                            "A reviewer will refine it before routing to the Decision Maker."
                        ),
                    }
                ],
            },
            {"type": "divider"},

            # ── Title ──────────────────────────────────────────────────
            {
                "type": "input",
                "block_id": BID_TITLE,
                "label": {"type": "plain_text", "text": "Decision Title"},
                "hint": {
                    "type": "plain_text",
                    "text": "A clear, concise statement of the decision needed.",
                },
                "element": {
                    "type": "plain_text_input",
                    "action_id": AID_TITLE,
                    "placeholder": {
                        "type": "plain_text",
                        "text": "e.g. Approve Q3 vendor contract renewal",
                    },
                    "max_length": 150,
                },
            },

            # ── Decision Type ──────────────────────────────────────────
            {
                "type": "input",
                "block_id": BID_TYPE,
                "label": {"type": "plain_text", "text": "Decision Type"},
                "element": {
                    "type": "static_select",
                    "action_id": AID_TYPE,
                    "placeholder": {"type": "plain_text", "text": "Select a type"},
                    "options": [
                        _opt("Strategic", "Strategic"),
                        _opt("Operational", "Operational"),
                        _opt("Investment", "Investment"),
                        _opt("Policy", "Policy"),
                        _opt("Other", "Other"),
                    ],
                },
            },

            # ── Sponsor ────────────────────────────────────────────────
            {
                "type": "input",
                "block_id": BID_SPONSOR,
                "label": {"type": "plain_text", "text": "Sponsor"},
                "hint": {
                    "type": "plain_text",
                    "text": "The leader accountable for this decision.",
                },
                "element": {
                    "type": "users_select",
                    "action_id": AID_SPONSOR,
                    "placeholder": {"type": "plain_text", "text": "Select a sponsor"},
                },
            },

            # ── Decision Maker ────────────────────────────────────────
            {
                "type": "input",
                "block_id": BID_DECISION_MAKER,
                "label": {"type": "plain_text", "text": "Decision Maker"},
                "hint": {
                    "type": "plain_text",
                    "text": "The person with authority to make this decision.",
                },
                "element": {
                    "type": "users_select",
                    "action_id": AID_DECISION_MAKER,
                    "placeholder": {
                        "type": "plain_text",
                        "text": "Select the decision maker",
                    },
                },
            },

            # ── Context ────────────────────────────────────────────────
            {
                "type": "input",
                "block_id": BID_CONTEXT,
                "label": {"type": "plain_text", "text": "Context & Background"},
                "hint": {
                    "type": "plain_text",
                    "text": (
                        "What is the problem/opportunity? "
                        "What constraints or dependencies exist?"
                    ),
                },
                "element": {
                    "type": "plain_text_input",
                    "action_id": AID_CONTEXT,
                    "multiline": True,
                    "placeholder": {
                        "type": "plain_text",
                        "text": "Provide as much context as possible…",
                    },
                    "max_length": 3000,
                },
            },

            # ── Links ──────────────────────────────────────────────────
            {
                "type": "input",
                "block_id": BID_LINKS,
                "label": {"type": "plain_text", "text": "Supporting Links"},
                "optional": True,
                "hint": {
                    "type": "plain_text",
                    "text": "Docs, slides, or tickets (one URL per line).",
                },
                "element": {
                    "type": "plain_text_input",
                    "action_id": AID_LINKS,
                    "multiline": True,
                    "placeholder": {
                        "type": "plain_text",
                        "text": "https://…",
                    },
                },
            },

            # ── Visibility ─────────────────────────────────────────────
            {
                "type": "input",
                "block_id": BID_VISIBILITY,
                "label": {"type": "plain_text", "text": "Visibility"},
                "hint": {
                    "type": "plain_text",
                    "text": (
                        "Public: visible to the whole org in #ics-decisions. "
                        "Restricted: DMs only."
                    ),
                },
                "element": {
                    "type": "radio_buttons",
                    "action_id": AID_VISIBILITY,
                    "initial_option": _opt("Public (default)", "Public"),
                    "options": [
                        _opt("Public (default)", "Public"),
                        _opt("Restricted (DMs only)", "Restricted"),
                    ],
                },
            },
        ],
    }


# ══════════════════════════════════════════════════════════════════════════
# Resolution Modal  (Phase 3 — defined here for completeness)
# ══════════════════════════════════════════════════════════════════════════

def build_resolution_modal(record_id: str) -> dict[str, Any]:
    """
    Modal presented to the Decision Maker when they click [Make Decision].
    `record_id` is carried in private_metadata so the submission handler
    can update the correct Airtable record.
    """
    return {
        "type": "modal",
        "callback_id": RESOLUTION_MODAL_ID,
        "private_metadata": record_id,
        "title": {"type": "plain_text", "text": "Record Decision"},
        "submit": {"type": "plain_text", "text": "Close Decision"},
        "close": {"type": "plain_text", "text": "Cancel"},
        "blocks": [
            {
                "type": "input",
                "block_id": BID_OUTCOME,
                "label": {"type": "plain_text", "text": "Decision Outcome"},
                "hint": {
                    "type": "plain_text",
                    "text": "e.g. Approved, Rejected, Deferred, Option A selected",
                },
                "element": {
                    "type": "plain_text_input",
                    "action_id": AID_OUTCOME,
                    "placeholder": {
                        "type": "plain_text",
                        "text": "State the decision in one sentence.",
                    },
                    "max_length": 200,
                },
            },
            {
                "type": "input",
                "block_id": BID_RATIONALE,
                "label": {"type": "plain_text", "text": "Rationale"},
                "element": {
                    "type": "plain_text_input",
                    "action_id": AID_RATIONALE,
                    "multiline": True,
                    "placeholder": {
                        "type": "plain_text",
                        "text": "Explain the reasoning behind this decision…",
                    },
                    "max_length": 3000,
                },
            },
        ],
    }


# ══════════════════════════════════════════════════════════════════════════
# Channel & DM message builders
# ══════════════════════════════════════════════════════════════════════════

def build_intake_channel_message(
    *,
    record_id: str,
    title: str,
    decision_type: str,
    priority: str,
    requester_id: str,
    sponsor_id: str,
    decision_maker_id: str,
    visibility: str,
    sla_deadline_str: str,
) -> list[dict[str, Any]]:
    """
    Root message posted to #ics-decisions when a new decision is submitted.
    Returns a list of blocks.
    """
    priority_emoji = {"P0": ":red_circle:", "P1": ":large_yellow_circle:", "P2": ":white_circle:"}.get(
        priority, ":white_circle:"
    )
    visibility_text = ":lock: Restricted" if visibility == "Restricted" else ":globe_with_meridians: Public"

    return [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": f"{priority_emoji} New Decision: {title}"},
        },
        {
            "type": "section",
            "fields": [
                _mrkdwn_field("*Type*", decision_type),
                _mrkdwn_field("*Priority*", priority),
                _mrkdwn_field("*Requester*", f"<@{requester_id}>"),
                _mrkdwn_field("*Sponsor*", f"<@{sponsor_id}>"),
                _mrkdwn_field("*Decision Maker*", f"<@{decision_maker_id}>"),
                _mrkdwn_field("*Visibility*", visibility_text),
                _mrkdwn_field("*SLA Deadline*", sla_deadline_str),
                _mrkdwn_field("*Airtable ID*", record_id),
            ],
        },
        {"type": "divider"},
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": ":hourglass_flowing_sand: Status: *DRAFTING* — AI draft being generated…",
                }
            ],
        },
    ]


def build_hitl_dm_message(
    *,
    record_id: str,
    title: str,
    decision_type: str,
    priority: str,
    requester_id: str,
    context_user: str,
    context_ai: str,
    recommendation_ai: str,
    options_ai: str,
    draft_due_str: str,
) -> list[dict[str, Any]]:
    """
    DM sent to the HITL reviewer with the AI draft and action buttons.
    """
    return [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": ":pencil: HITL Review Required"},
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"A new decision needs your review before routing.\n\n"
                    f"*Title:* {title}\n"
                    f"*Type:* {decision_type}  |  *Priority:* {priority}\n"
                    f"*Requester:* <@{requester_id}>\n"
                    f"*Draft Due:* {draft_due_str}"
                ),
            },
        },
        {"type": "divider"},
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": "*:bust_in_silhouette: User Context*"},
        },
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": context_user[:2900]},
        },
        {"type": "divider"},
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": "*:robot_face: AI Summary*"},
        },
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": context_ai[:2900]},
        },
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": "*:bulb: AI Recommendation*"},
        },
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": recommendation_ai[:2900]},
        },
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": "*:bar_chart: Options Considered*"},
        },
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": options_ai[:2900]},
        },
        {"type": "divider"},
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": ":white_check_mark: Approve & Route"},
                    "style": "primary",
                    "action_id": "hitl_approve",
                    "value": record_id,
                    "confirm": {
                        "title": {"type": "plain_text", "text": "Approve this draft?"},
                        "text": {
                            "type": "mrkdwn",
                            "text": "This will route the decision to the Decision Maker and Sponsor.",
                        },
                        "confirm": {"type": "plain_text", "text": "Yes, approve"},
                        "deny": {"type": "plain_text", "text": "Not yet"},
                    },
                },
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": ":speech_balloon: Request More Info"},
                    "action_id": "hitl_request_info",
                    "value": record_id,
                },
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": ":pencil2: Edit Draft"},
                    "action_id": "hitl_edit_draft",
                    "value": record_id,
                },
            ],
        },
    ]


def build_pending_decision_dm_message(
    *,
    record_id: str,
    title: str,
    context_ai: str,
    recommendation_ai: str,
    options_ai: str,
    sla_deadline_str: str,
) -> list[dict[str, Any]]:
    """
    DM sent to Decision Maker + Sponsor when a decision is ready.
    """
    return [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": ":triangular_flag_on_post: Decision Needed"},
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"*{title}*\n\n"
                    f"This decision has been reviewed and is ready for your input.\n"
                    f"*SLA Deadline:* {sla_deadline_str}"
                ),
            },
        },
        {"type": "divider"},
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*:robot_face: AI Summary*\n{context_ai[:1400]}"},
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*:bulb: Recommendation*\n{recommendation_ai[:1400]}",
            },
        },
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*:bar_chart: Options*\n{options_ai[:1400]}"},
        },
        {"type": "divider"},
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": ":ballot_box_with_check: Make Decision"},
                    "style": "primary",
                    "action_id": "make_decision",
                    "value": record_id,
                }
            ],
        },
    ]


def build_closed_thread_message(
    *,
    outcome: str,
    rationale: str,
    decision_maker_id: str,
) -> list[dict[str, Any]]:
    """Thread reply posted to #ics-decisions when a decision is closed."""
    return [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": ":white_check_mark: Decision Closed"},
        },
        {
            "type": "section",
            "fields": [
                _mrkdwn_field("*Outcome*", outcome),
                _mrkdwn_field("*Decided by*", f"<@{decision_maker_id}>"),
            ],
        },
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*Rationale*\n{rationale}"},
        },
    ]


# ══════════════════════════════════════════════════════════════════════════
# Edit Draft Modal  (HITL reviewer edits AI-generated fields)
# ══════════════════════════════════════════════════════════════════════════

def build_edit_draft_modal(
    *,
    record_id: str,
    context_ai: str,
    recommendation_ai: str,
    options_ai: str,
) -> dict[str, Any]:
    """
    Pre-populated modal for the HITL reviewer to edit AI draft fields.
    `record_id` is stored in private_metadata for the submission handler.
    """
    return {
        "type": "modal",
        "callback_id": EDIT_DRAFT_MODAL_ID,
        "private_metadata": record_id,
        "title": {"type": "plain_text", "text": "Edit AI Draft"},
        "submit": {"type": "plain_text", "text": "Save Changes"},
        "close": {"type": "plain_text", "text": "Cancel"},
        "blocks": [
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": (
                            ":pencil2: Edit the AI-generated fields below. "
                            "After saving, you can approve and route the decision."
                        ),
                    }
                ],
            },
            {"type": "divider"},
            {
                "type": "input",
                "block_id": BID_CONTEXT_AI,
                "label": {"type": "plain_text", "text": "AI Context Summary"},
                "element": {
                    "type": "plain_text_input",
                    "action_id": AID_CONTEXT_AI,
                    "multiline": True,
                    "initial_value": context_ai[:3000],
                    "max_length": 3000,
                },
            },
            {
                "type": "input",
                "block_id": BID_RECOMMENDATION_AI,
                "label": {"type": "plain_text", "text": "AI Recommendation"},
                "element": {
                    "type": "plain_text_input",
                    "action_id": AID_RECOMMENDATION_AI,
                    "multiline": True,
                    "initial_value": recommendation_ai[:3000],
                    "max_length": 3000,
                },
            },
            {
                "type": "input",
                "block_id": BID_OPTIONS_AI,
                "label": {"type": "plain_text", "text": "Options Considered"},
                "element": {
                    "type": "plain_text_input",
                    "action_id": AID_OPTIONS_AI,
                    "multiline": True,
                    "initial_value": options_ai[:3000],
                    "max_length": 3000,
                },
            },
        ],
    }


# ── Private helpers ────────────────────────────────────────────────────────

def _opt(label: str, value: str) -> dict[str, Any]:
    return {"text": {"type": "plain_text", "text": label}, "value": value}


def _mrkdwn_field(label: str, value: str) -> dict[str, Any]:
    return {"type": "mrkdwn", "text": f"{label}\n{value}"}
