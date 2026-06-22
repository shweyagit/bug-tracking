# Bug Tracking Agent

An enterprise-grade bug intelligence platform that connects GitHub Actions CI pipelines, Jira, and Claude AI to automate the full bug lifecycle — from detection to ticket creation to verification.

> Built for teams that ship fast and need bugs caught, structured, and tracked automatically.

---

## Demo

> Describing a bug in plain English → AI structures it → Playwright verifies it on the live app → pushed to Jira with screenshots attached.

**Report a Bug — plain English → AI-structured Jira ticket**

![Report a Bug](docs/report-bug.png)

> **Watch the full workflow:** [demo.mp4](docs/demo.mp4)
>
**Live Jira Bug Tracker — color-coded by priority, synced live**

![Jira Tracker](docs/jira-tracker.png)

---

## What It Does

### CI Pipeline Integration
When a GitHub Actions workflow fails, the agent automatically:
- Receives the failure event via a secured webhook (HMAC-SHA256 validated)
- Downloads JUnit XML test artifacts directly from GitHub Actions
- Parses every failing test case with full stack traces
- Sends failures to Claude AI for structured bug analysis
- Creates a draft bug ticket in the dashboard for engineer review
- One click to push the fully-formed ticket to Jira — with stack traces, affected feature, severity, and labels

### Manual Bug Reporting — UI Bugs
Any team member can report a UI bug in plain English:
- Claude AI converts the description into a structured, professional Jira ticket
- Attach screenshots, screen recordings, or zip bundles
- **Record reproduction steps** — a Playwright browser opens on your machine, records every click and navigation, then replays them headlessly to capture a full Playwright trace (screenshots at every action + network logs + console errors)
- The trace attaches to the Jira ticket automatically — open it at [trace.playwright.dev](https://trace.playwright.dev) to replay the bug step by step

### Manual Bug Reporting — API Bugs
A built-in Postman-style request builder lets you fire live API calls and capture evidence directly:
- Select **Environment** (Production / Staging / Development / Local) — base URL auto-fills from env vars
- Choose **method**, enter the **full URL**, add or remove **headers**, write the **request body**
- Click **Send** — the response (status, body, headers, latency) is captured in the dashboard
- Describe what's wrong, click **Draft Bug Ticket** — Claude gets the full request + response + headers and writes a developer-ready ticket with curl-reproducible steps
- Push to Jira with all evidence included

### Live Jira Bug Tracker
- Pulls all bugs live from Jira — no manual sync
- Colour-coded by priority (Critical → High → Medium → Low)
- Filter by status, priority, label, or search by title
- Clickable cards link directly to Jira tickets

### Feature Health Dashboard
- Tracks which features fail most frequently across CI runs
- Failure rate % per feature area
- Most flaky tests ranked by failure count
- 30-day failure trend charts

### Release Bug Tracking
- Tag bugs in Jira with a version label (e.g. `v1.2.0`)
- Enter that version in the dashboard to instantly see all bugs scoped to that release
- Release readiness score: total bugs, still open, fixed, % complete
- Bugs split into **Still Open** and **Fixed** tabs

---

## Architecture

```
GitHub Actions (CI fails)
        │
        ▼ webhook (HMAC-SHA256)
FastAPI Webhook Service
        │
        ▼
Redis Queue (ARQ)
        │
        ▼
Background Worker
  ├── Downloads JUnit XML artifacts from GitHub
  ├── Parses test failures + stack traces
  ├── Claude AI analysis → structured bug draft
  └── Saved to PostgreSQL
        │
        ▼
Streamlit Dashboard
  ├── Review & push CI bug drafts to Jira
  ├── UI bug reporting — plain English + Playwright recording → AI → Jira
  ├── API bug reporting — live request builder → AI → Jira
  ├── Live Jira tracker
  ├── Feature health & failure trends
  └── Release tracking by Jira label
```

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python, FastAPI |
| AI | Claude Sonnet (Anthropic) — analysis + vision |
| Dashboard | Streamlit |
| Database | PostgreSQL |
| Queue | Redis + ARQ |
| Browser Automation | Playwright (Chromium) |
| HTTP Client | httpx |
| Deployment | Docker Compose |
| Integrations | GitHub Actions, Jira REST API v3 |

---

## Dashboard Pages

| Page | Description |
|------|-------------|
| **Home** | Summary metrics — draft bugs, open bugs, recent CI failures |
| **Test Failures** | Browse CI test failures, filter by branch or feature area |
| **Bug Tickets** | Review AI-drafted CI bugs, push to Jira with full stack traces |
| **Feature Health** | Failure rates per feature, flaky test ranking, 30-day trend |
| **Release Bugs** | Enter a version label → see all Jira bugs for that release, open vs fixed |
| **Report a Bug** | UI bug with Playwright recording or API bug with live request builder → AI → Jira |
| **Jira Tracker** | Live bug board pulled from Jira, colour-coded by priority |

> **User Manual** and **About This App** are accessible via popup buttons in the top-right corner of every page.

---

## Environment Variables

| Variable | Description |
|----------|-------------|
| `PROD_BASE_URL` | Base URL for Production API (default: `https://api.sportiq.com`) |
| `STAGING_BASE_URL` | Base URL for Staging API |
| `DEV_BASE_URL` | Base URL for Development API |
| `LOCAL_BASE_URL` | Base URL for Local API (default: `http://localhost:3000`) |
| `ANTHROPIC_API_KEY` | Claude AI API key |
| `JIRA_BASE_URL` | Your Jira workspace URL |
| `JIRA_EMAIL` | Jira account email |
| `JIRA_API_TOKEN` | Jira API token |
| `JIRA_PROJECT_KEY` | Jira project key (default: `SCRUM`) |
| `DATABASE_URL` | PostgreSQL connection string |
| `VERIFY_SERVICE_URL` | Local verify agent URL (default: `http://host.docker.internal:8502`) |

See `.env.example` for the full configuration required to run your own instance.

---

## Note

This project runs against a private Jira workspace, GitHub repo, and locally hosted app — credentials are not included.
