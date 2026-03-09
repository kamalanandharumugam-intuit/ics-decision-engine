"""
Anthropic Claude integration for generating AI decision drafts.

The prompt instructs the model to return a strict JSON payload so the
calling code can parse fields without fragile text parsing.
"""
from __future__ import annotations

import json
import logging
from typing import TypedDict

import anthropic

import config

logger = logging.getLogger(__name__)

_client: anthropic.Anthropic | None = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    return _client


# ── Return type ────────────────────────────────────────────────────────────

class AIDraft(TypedDict):
    context_ai: str        # Condensed, neutral summary of the user's context
    recommendation_ai: str # A clear, actionable recommendation
    options_ai: str        # Markdown list of options with pros/cons


_FALLBACK: AIDraft = {
    "context_ai": "(AI summary unavailable — please review user context above.)",
    "recommendation_ai": "(AI recommendation unavailable.)",
    "options_ai": "(AI options unavailable.)",
}

# ── System prompt ──────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """\
You are an expert Chief of Staff supporting a technology organization. \
Your role is to help accelerate decisions by producing clear, unbiased decision briefs.

You will receive a structured decision request and must reply with ONLY a valid JSON object \
— no markdown fences, no prose outside the JSON — with exactly these three keys:

{
  "context_ai": "<string>",
  "recommendation_ai": "<string>",
  "options_ai": "<string>"
}

Guidelines:
- context_ai: A concise (3–5 sentence) neutral summary that distills the user's context. \
  Highlight the core problem, key constraints, and who is affected.
- recommendation_ai: A clear, direct recommendation (1–3 sentences). \
  State what you recommend and the primary reason. Do not hedge excessively.
- options_ai: A markdown-formatted list of 2–4 realistic options, each with 1–2 bullet pros \
  and 1–2 bullet cons. Example format:
  **Option A — Do X**
  - Pro: …
  - Con: …

  **Option B — Do Y**
  - Pro: …
  - Con: …

Be concise. Decision-makers are busy. Prefer clarity over comprehensiveness.
"""


# ── Main generation function ───────────────────────────────────────────────

def generate_decision_draft(
    *,
    title: str,
    decision_type: str,
    context_user: str,
    sponsor_slack_id: str,
    priority: str,
) -> AIDraft:
    """
    Call Claude to generate a structured decision draft.

    Returns an AIDraft dict. On any API failure, returns _FALLBACK so the
    workflow can continue without an LLM response.
    """
    user_message = f"""\
Decision Title: {title}
Decision Type: {decision_type}
Priority: {priority}
Sponsor Slack ID: {sponsor_slack_id}

--- User-provided context ---
{context_user}
---

Please generate the decision brief as specified.
"""

    try:
        client = _get_client()
        message = client.messages.create(
            model=config.ANTHROPIC_MODEL,
            max_tokens=1500,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
        )

        raw_text = message.content[0].text.strip()
        logger.info("LLM response received (%d chars)", len(raw_text))

        draft = _parse_draft(raw_text)
        return draft

    except anthropic.APITimeoutError:
        logger.error("Anthropic API timed out for decision '%s'", title)
        return _FALLBACK
    except anthropic.APIError as exc:
        logger.error("Anthropic API error for '%s': %s", title, exc, exc_info=True)
        return _FALLBACK
    except Exception as exc:
        logger.error("Unexpected LLM error for '%s': %s", title, exc, exc_info=True)
        return _FALLBACK


def _parse_draft(raw: str) -> AIDraft:
    """
    Parse the model's JSON response.
    Strips markdown code fences if the model ignores the no-fence instruction.
    """
    # Strip ```json ... ``` fences defensively
    text = raw
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(
            line for line in lines if not line.startswith("```")
        ).strip()

    data = json.loads(text)

    return AIDraft(
        context_ai=str(data.get("context_ai", _FALLBACK["context_ai"])),
        recommendation_ai=str(data.get("recommendation_ai", _FALLBACK["recommendation_ai"])),
        options_ai=str(data.get("options_ai", _FALLBACK["options_ai"])),
    )
