# ICS AI-Powered Decision Acceleration Tool

A Slack-native workflow engine that accelerates organizational decision-making by combining human judgment with AI-assisted drafting. Decisions move from intake to resolution within a **4 business day SLA**, with full transparency, accountability, and audit trail in Airtable.

---

## Table of Contents

- [Overview](#overview)
- [How It Works](#how-it-works)
- [Architecture](#architecture)
- [Project Structure](#project-structure)
- [State Machine](#state-machine)
- [Airtable Schema](#airtable-schema)
- [SLA Rules](#sla-rules)
- [Setup & Installation](#setup--installation)
- [Running Locally](#running-locally)
- [Slack App Configuration](#slack-app-configuration)
- [Environment Variables](#environment-variables)
- [API Endpoints](#api-endpoints)
- [Deploying to Production](#deploying-to-production)

---

## Overview

### The Problem
Decision-making in large organizations is slow. Requests get lost in Slack threads, accountability is unclear, and there is no single source of truth for the status of a decision.

### The Solution
This tool provides a structured, automated workflow entirely inside Slack:

1. Anyone submits a decision request via `/decision new`
2. Claude AI instantly generates a decision brief (context summary, recommendation, options)
3. A designated reviewer (HITL) reviews and approves the draft
4. The Decision Maker is routed the brief with a single button to record their decision
5. The decision is logged in Airtable and summarized back to the Slack channel
6. If anyone misses their deadline, automated nudges and escalations fire automatically

---

## How It Works

### End-to-End Flow

```
User types /decision new
        │
        ▼
┌─────────────────────────┐
│   Slack Modal Opens     │  Fields: Title, Type, Sponsor,
│   (Intake Form)         │  Decision Maker, Context, Visibility
└──────────┬──────────────┘
           │ Submit
           ▼
┌─────────────────────────┐
│  Airtable Record        │  Status: DRAFTING
│  Created                │  Draft Due: +2 business days
│                         │  SLA Deadline: +4 business days
└──────────┬──────────────┘
           │
           ▼
┌─────────────────────────┐
│  Claude AI Generates    │  - Context Summary
│  Decision Brief         │  - Recommendation
│                         │  - Options with Pros/Cons
└──────────┬──────────────┘
           │
           ▼
┌─────────────────────────┐
│  HITL Reviewer          │  Status: HITL_REVIEW
│  receives DM            │  Buttons:
│                         │  ✅ Approve & Route
│                         │  💬 Request More Info
│                         │  ✏️  Edit Draft
└──────────┬──────────────┘
           │ Approve & Route
           ▼
┌─────────────────────────┐
│  Decision Maker +       │  Status: PENDING_DECISION
│  Sponsor receive DM     │  Button: ✅ Make Decision
└──────────┬──────────────┘
           │ Make Decision
           ▼
┌─────────────────────────┐
│  Resolution Modal       │  Fields: Outcome, Rationale
│  Opens                  │
└──────────┬──────────────┘
           │ Submit
           ▼
┌─────────────────────────┐
│  Decision CLOSED        │  Status: CLOSED
│                         │  Summary posted to #ics-decisions
│                         │  Requester + Sponsor notified
└─────────────────────────┘
```

---

## Architecture

```
┌──────────────────────────────────────────────────────────┐
│                     Slack Workspace                      │
│         /decision · buttons · modals · DMs               │
└────────────────────────┬─────────────────────────────────┘
                         │ HTTPS
                         ▼
┌──────────────────────────────────────────────────────────┐
│                    FastAPI (app.py)                      │
│                                                          │
│  POST /slack/commands       ─┐                           │
│  POST /slack/interactivity  ─┼─► Slack Bolt Dispatcher  │
│  POST /slack/events         ─┘   (verifies signatures)  │
│                                                          │
│  POST /internal/run_sla_checks  ◄── External Cron        │
│  GET  /health                                            │
└────────────┬─────────────────────────────────────────────┘
             │
     ┌───────┴────────┐
     │                │
  ack() < 3s     Background Thread
  (required       (daemon=True)
  by Slack)            │
                  ┌────┴─────────────┐
                  │                  │
           Airtable API       Anthropic API
           (pyairtable)       (claude-sonnet-4-6)
           Single source      AI draft generation
           of truth
```

### Key Design Principles

**3-Second ACK Pattern**
Slack requires all handlers to respond within 3 seconds or it retries. Every handler calls `ack()` immediately to close the Slack timeout, then spawns a background thread for all heavy work (Airtable writes, LLM calls, Slack DMs).

**Stateless Application**
No local database. All state lives in Airtable. The app can be restarted, scaled, or run as ephemeral containers without losing any data.

**AI-Assisted, Not AI-Replaced**
Claude generates the draft — a human reviewer (HITL) must approve before anything reaches the Decision Maker. The AI is a productivity accelerator, not a decision-maker.

**Idempotent SLA Nudges**
The `Nudges Sent` field in Airtable stores a JSON object of flags. Before sending any nudge, the engine checks this field. Duplicate nudges can never fire regardless of how many times the cron runs.

---

## Project Structure

```
ics-decision-engine/
│
├── app.py                  # Entry point — FastAPI app + all Bolt listener registrations
├── config.py               # Environment variable loader (fails fast on missing vars)
├── requirements.txt        # Pinned Python dependencies
├── .env.example            # Template for required environment variables
│
├── handlers/               # Business logic — one file per concern
│   ├── commands.py         # /decision slash command handler
│   ├── modals.py           # Intake + Resolution modal submission handlers
│   ├── actions.py          # Interactive button handlers (HITL + Make Decision)
│   └── sla.py              # SLA check engine (nudges + escalation)
│
└── utils/                  # Shared utilities
    ├── slack_ui.py         # All Block Kit surfaces (modals + messages)
    ├── airtable_client.py  # Airtable CRUD + field name constants
    ├── business_days.py    # Business-day arithmetic (LA timezone, Mon–Fri)
    └── llm.py              # Anthropic Claude prompt + JSON response parsing
```

### Module Responsibilities

| File | Responsibility |
|---|---|
| `app.py` | Mounts FastAPI routes, registers all Bolt listeners, wires SLA endpoint |
| `config.py` | Loads and validates all env vars at startup; single import for all modules |
| `handlers/commands.py` | Opens intake modal on `/decision new`; shows help on `/decision help` |
| `handlers/modals.py` | Processes form submissions; orchestrates Airtable + LLM + Slack DMs |
| `handlers/actions.py` | Handles all button clicks; opens Edit Draft and Resolution modals |
| `handlers/sla.py` | Queries open Airtable records; fires idempotent nudges; escalates overdue decisions |
| `utils/slack_ui.py` | Single source of truth for all Block Kit JSON — modals and message blocks |
| `utils/airtable_client.py` | All Airtable reads/writes; field name constants; `record_nudge()` idempotency |
| `utils/business_days.py` | `add_business_days()`, `is_past_due()`, `now_la()` using Python `zoneinfo` |
| `utils/llm.py` | Builds Claude prompt; parses structured JSON response; graceful fallback on error |

---

## State Machine

```
                    /decision new
                          │
                          ▼
                   INTAKE_RECEIVED
                          │
                          ▼
                       DRAFTING  ◄─── LLM generating draft
                          │
                          ▼
                     HITL_REVIEW  ◄─── Reviewer editing/requesting info
                          │
                    Approve & Route
                          │
                          ▼
                  PENDING_DECISION  ◄─── Awaiting Decision Maker
                          │
                     Make Decision
                          │
                          ▼
                        CLOSED


    Any open state ──────────────────► ESCALATED  (SLA breached)
    Any open state ──────────────────► CANCELED   (manually canceled)
```

---

## Airtable Schema

Table Name: **`Decisions`**

| Field | Type | Description |
|---|---|---|
| Decision ID | Auto-number | Unique identifier |
| Status | Single select | Current state machine status |
| Visibility | Single select | `Public` or `Restricted` |
| Decision Title | Single line text | Short description of the decision |
| Decision Type | Single select | `Strategic`, `Operational`, `Investment`, `Policy`, `Other` |
| Priority | Single select | `P0`, `P1`, `P2` — bot-assigned from type |
| Requester Slack ID | Single line text | Slack user ID of submitter |
| Sponsor Slack ID | Single line text | Slack user ID of sponsor |
| Decision Maker Slack ID | Single line text | Slack user ID of decision maker |
| HITL Reviewer Slack ID | Single line text | Slack user ID of assigned reviewer |
| Date Submitted | Date/Time | Timestamp of intake submission |
| Draft Due | Date/Time | `Date Submitted` + 2 business days |
| SLA Deadline | Date/Time | `Date Submitted` + 4 business days |
| Context Summary (User) | Long text | Raw context provided by requester |
| Context Summary (AI) | Long text | Claude-generated condensed summary |
| Recommendation (AI) | Long text | Claude-generated recommendation |
| Options (AI) | Long text | Claude-generated options with pros/cons |
| Outcome | Single line text | Final decision recorded by Decision Maker |
| Rationale | Long text | Reasoning provided by Decision Maker |
| Slack Thread TS | Single line text | Slack message timestamp for thread replies |
| Nudges Sent | Long text | JSON object of fired nudge flags (idempotency) |

### Priority Assignment (bot-assigned)

| Decision Type | Priority |
|---|---|
| Strategic | P0 |
| Investment | P0 |
| Policy | P1 |
| Operational | P1 |
| Other | P2 |

---

## SLA Rules

All SLA calculations use **business days only** (Monday–Friday), in the **America/Los_Angeles** timezone.

| Nudge Key | Trigger Condition | Recipients |
|---|---|---|
| `draft_overdue` | Draft Due (day 2) has passed; status still pre-PENDING | HITL Reviewer |
| `sla_day3_nudge` | ≤ 1 business day before SLA deadline; status `PENDING_DECISION` | Decision Maker + Sponsor |
| `sla_overdue` | SLA Deadline (day 4) has passed | All parties |
| `escalated` | `sla_overdue` already fired on a prior cron run | All parties + #ics-decisions |

When `escalated` fires, the Airtable record status is also set to `ESCALATED`.

---

## Setup & Installation

### Prerequisites

- Python 3.10+
- A [Slack App](https://api.slack.com/apps) with a bot token
- An [Anthropic API key](https://console.anthropic.com)
- An [Airtable base](https://airtable.com) with the schema above
- [ngrok](https://ngrok.com) (for local development)

### Install

```bash
git clone https://github.com/kamalanandharumugam-intuit/ics-decision-engine.git
cd ics-decision-engine

# Create and activate a virtual environment (recommended)
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### Configure

```bash
cp .env.example .env
```

Open `.env` and fill in all required values (see [Environment Variables](#environment-variables) below).

---

## Running Locally

```bash
# Start the server
uvicorn app:api --reload --port 8000
```

In a second terminal, expose it to Slack:

```bash
ngrok http 8000
```

Copy the `https://xxxx.ngrok.io` URL — you'll need it for Slack app configuration.

---

## Slack App Configuration

In your [Slack App settings](https://api.slack.com/apps):

### 1. OAuth & Permissions
Add these **Bot Token Scopes**:

| Scope | Purpose |
|---|---|
| `chat:write` | Post messages and DMs |
| `chat:write.public` | Post to channels the bot hasn't joined |
| `commands` | Receive slash commands |
| `users:read` | Look up user info |
| `im:write` | Open DM channels |

### 2. Slash Commands
Create a new command:
- **Command:** `/decision`
- **Request URL:** `https://<your-ngrok-url>/slack/commands`
- **Short Description:** `Submit a new decision request`
- **Usage Hint:** `new`

### 3. Interactivity & Shortcuts
- **Enable Interactivity:** On
- **Request URL:** `https://<your-ngrok-url>/slack/interactivity`

### 4. Event Subscriptions
- **Enable Events:** On
- **Request URL:** `https://<your-ngrok-url>/slack/events`

### 5. Install the App
Go to **Install App** → **Install to Workspace** → copy the `Bot User OAuth Token` into your `.env`.

---

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `SLACK_BOT_TOKEN` | Yes | Bot User OAuth Token (`xoxb-...`) from Slack App → OAuth & Permissions |
| `SLACK_SIGNING_SECRET` | Yes | From Slack App → Basic Information → Signing Secret |
| `ANTHROPIC_API_KEY` | Yes | From [console.anthropic.com](https://console.anthropic.com) |
| `AIRTABLE_API_KEY` | Yes | Personal Access Token (`pat...`) from Airtable account settings |
| `AIRTABLE_BASE_ID` | Yes | The `app...` ID from your Airtable base URL |
| `AIRTABLE_TABLE_NAME` | No | Table name (default: `Decisions`) |
| `DECISIONS_CHANNEL` | No | Channel to post decisions (default: `#ics-decisions`) |
| `HITL_REVIEWER_SLACK_ID` | Yes | Slack user ID (`U...`) of the default HITL reviewer |
| `ANTHROPIC_MODEL` | No | Claude model to use (default: `claude-sonnet-4-6`) |
| `INTERNAL_API_SECRET` | No | Bearer token for `/internal/run_sla_checks` (localhost-only if unset) |
| `PORT` | No | Server port (default: `8000`) |

---

## API Endpoints

| Method | Path | Description |
|---|---|---|
| `POST` | `/slack/commands` | Receives Slack slash command payloads |
| `POST` | `/slack/interactivity` | Receives button clicks and modal submissions |
| `POST` | `/slack/events` | Receives Slack Events API payloads |
| `POST` | `/internal/run_sla_checks` | Triggers SLA check — call on a cron schedule |
| `GET` | `/health` | Health check — returns `{"status": "ok"}` |

### SLA Cron Endpoint

Call `/internal/run_sla_checks` on a schedule, e.g. every 30 minutes during business hours (Mon–Fri, 07:00–19:00 PT).

```bash
# Example curl call
curl -X POST http://localhost:8000/internal/run_sla_checks

# With auth token (if INTERNAL_API_SECRET is set)
curl -X POST https://your-domain.com/internal/run_sla_checks \
  -H "Authorization: Bearer your-secret-token"
```

Returns:
```json
{ "status": "ok", "nudges_sent": 3 }
```

---

## Deploying to Production

The app is a standard ASGI app — deploy anywhere that runs Python.

### Option A — Any Linux Server / VM

```bash
pip install -r requirements.txt
uvicorn app:api --host 0.0.0.0 --port 8000 --workers 2
```

Use `nginx` as a reverse proxy and `systemd` or `supervisor` to keep it running.

### Option B — Docker

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
CMD ["uvicorn", "app:api", "--host", "0.0.0.0", "--port", "8000"]
```

### Option C — Cloud Run / Railway / Render / Fly.io

All support deploying directly from this GitHub repo. Set your environment variables in the platform's secrets manager.

### SLA Cron in Production

Use any scheduler to call `/internal/run_sla_checks`:

- **GitHub Actions** — scheduled workflow (free)
- **Google Cloud Scheduler**
- **AWS EventBridge**
- **cron** on the host server

Example GitHub Actions schedule:

```yaml
on:
  schedule:
    - cron: '*/30 14-23 * * 1-5'  # Every 30 min, Mon-Fri 07:00-16:00 PT (UTC-7)
jobs:
  sla:
    runs-on: ubuntu-latest
    steps:
      - run: |
          curl -X POST ${{ secrets.APP_URL }}/internal/run_sla_checks \
            -H "Authorization: Bearer ${{ secrets.INTERNAL_API_SECRET }}"
```

---

## Tech Stack

| | |
|---|---|
| **Language** | Python 3.12 |
| **Web Framework** | [FastAPI](https://fastapi.tiangolo.com) + [Uvicorn](https://www.uvicorn.org) |
| **Slack SDK** | [Slack Bolt for Python](https://slack.dev/bolt-python/) |
| **AI** | [Anthropic Claude](https://www.anthropic.com) (`claude-sonnet-4-6`) |
| **Database** | [Airtable](https://airtable.com) via [pyairtable](https://pyairtable.readthedocs.io) |
| **Config** | [python-dotenv](https://pypi.org/project/python-dotenv/) |

---

## Contributing

1. Fork the repo
2. Create a feature branch: `git checkout -b feature/my-change`
3. Commit your changes: `git commit -m "Add my change"`
4. Push and open a Pull Request

---

## License

MIT
