# Bug Tracking Agent

An enterprise-grade bug intelligence platform that connects GitHub Actions CI pipelines, Jira, and Claude AI to automate the full bug lifecycle — from detection to ticket creation to verification.

> Built for teams that ship fast and need bugs caught, structured, and tracked automatically.

---

## Demo

> Describing a bug in plain English → AI structures it → Playwright verifies it on the live app → pushed to Jira with screenshots attached.

**Report a Bug — plain English → AI-structured Jira ticket**

![Report a Bug](docs/report-bug.png)

> **Watch the full workflow:** [demo.mov](docs/demo.mov)
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

### Manual Bug Reporting
Any team member can report a bug in plain English:
- Claude AI converts the description into a structured, professional Jira ticket
- Attach screenshots, screen recordings, or zip bundles
- **Verify Bug on App** — a headless Playwright browser follows the reproduction steps on the real app, screenshots every step, and Claude vision confirms whether the bug is reproducible
- Console errors are captured automatically
- Everything (report + screenshots + console errors) is attached to the Jira ticket in one push

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
  ├── Manual bug reporting (plain English → AI → Jira)
  ├── Playwright bug verification on real app
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
| **Report a Bug** | Plain English → AI → Jira ticket, with Playwright verification |
| **Jira Tracker** | Live bug board pulled from Jira, colour-coded by priority |

---

## Note

This project runs against a private Jira workspace, GitHub repo, and locally hosted app — credentials are not included. See `.env.example` for the configuration required to run your own instance.
