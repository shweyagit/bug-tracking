import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from utils import ICON, page_setup

import streamlit as st

st.set_page_config(page_title="User Manual", page_icon=ICON, layout="wide")
page_setup()

st.title("User Manual")
st.markdown("Everything you need to use the SportIQ Bug Tracker effectively.")

st.divider()

# ── Getting Started ────────────────────────────────────────────────────────────
st.header("Getting Started")
st.markdown("""
Start the full stack with a single command from the project root:
```bash
./start.sh
```
This starts:
- The dashboard at **http://localhost:8501**
- The local verify agent on **port 8502** (handles browser recording & tracing)
- ngrok tunnel for external access

Check the sidebar — **Local Agent** should show 🟢 connected.
If it shows 🔴 offline, run `python verify_service.py` manually in a terminal.
""")

st.divider()

# ── Reporting a UI Bug ─────────────────────────────────────────────────────────
st.header("Reporting a UI Bug")

col1, col2 = st.columns([1, 1], gap="large")
with col1:
    st.subheader("Step 1 — Record the bug")
    st.markdown("""
Go to **Report Bug → UI Bug tab**.

Open **Record reproduction steps** and click **Record Steps**.
A browser opens on your machine — navigate to the app and reproduce the bug exactly as a user would.
Close the browser when done.

Click **Finish Recording**. The agent will:
- Convert your actions into numbered natural language steps
- Replay them headlessly to capture a **Playwright trace**

The trace is attached to the Jira ticket automatically — no extra work needed.
    """)
    st.info("The Playwright trace contains screenshots at every action, full network logs, and console errors. Open it at trace.playwright.dev to replay the bug.")

with col2:
    st.subheader("Step 2 — Draft the ticket")
    st.markdown("""
Review the recorded steps — **edit or remove** any that were captured incorrectly.

Describe the bug in plain English in the **Describe the bug** field (required).

Add any supporting files via the **drag & drop uploader** — screenshots, screen recordings, or zip bundles.

Enter your name, then click **Draft Bug Ticket**.

Claude AI will structure the report into:
- A clear title
- Numbered reproduction steps
- Expected vs actual behaviour
- Priority and labels
- Affected feature
    """)

st.subheader("Step 3 — Review & Push")
st.markdown("""
Review the AI-generated draft. You can:
- Edit the title, description, any step
- Add or remove steps with the **+** / **✕** buttons
- Change priority
- Adjust labels and affected feature

When satisfied, click **Push to Jira**. The ticket is created with the Playwright trace and any attachments included.
""")

st.divider()

# ── Reporting an API Bug ───────────────────────────────────────────────────────
st.header("Reporting an API Bug")

st.subheader("Option A — Manual entry")
st.markdown("""
Go to **Report Bug → API Bug tab**.

Fill in:
| Field | Example |
|-------|---------|
| Environment | Production |
| Method | POST |
| Endpoint | /api/compare |
| Request body | `{"player1": "Vozinha", "player2": "Messi", "sport": "football"}` |
| Response status | 200 |
| Response body | `{"player1": {"rating": "4/10", ...}}` |
| Additional context | Fabricated data returned instead of 404 |

Click **Draft Bug Ticket** — AI formats the ticket with curl-reproducible steps, then push to Jira.
""")

st.subheader("Option B — Run API Tests (recommended)")
st.markdown("""
Open **Run API tests — auto-detect failures** and click **Run API Tests**.

The agent runs the full SportIQ API test suite via Newman (~2 minutes).
Any failing request appears as a card showing the endpoint and assertion that failed.

Click **Draft** on any failure — the form auto-fills with all evidence.
Click **Draft Bug Ticket** → review → **Push to Jira**.

No file uploads. No copy-paste. The agent does it all.
""")

st.divider()

# ── Dashboard Pages ────────────────────────────────────────────────────────────
st.header("Dashboard Pages")

pages = {
    "Test Failures": "Latest CI run failures from GitHub Actions with AI root-cause analysis. See which tests are failing and why.",
    "Bug Tickets": "All draft and open bug tickets. Review AI-generated reports before they are pushed to Jira.",
    "Feature Health": "Which features fail most frequently across all test runs. Useful for sprint planning.",
    "Release Bugs": "Bugs that were open at the time of each release. Tracks quality at release gates.",
    "Report Bug": "File a new bug — UI flow with browser recording or API flow with Newman integration.",
    "Jira Tracker": "Browse bugs already pushed to your Jira board directly from the dashboard.",
}

for name, desc in pages.items():
    st.markdown(f"**{name}** — {desc}")

st.divider()

# ── Tips ───────────────────────────────────────────────────────────────────────
st.header("Tips")
st.markdown("""
- **Playwright trace** — download `playwright_trace.zip` from the Jira ticket and open it at [trace.playwright.dev](https://trace.playwright.dev) to replay every click, see network calls, and inspect console errors
- **Newman tests** — the collection file `SportIQ_API.postman_collection.json` is in the project root; import it into Postman to run or edit individual tests
- **Recording tips** — record only the steps needed to trigger the bug; avoid clicking around after the bug appears, as those actions will also be captured
- **API bug priority** — if environment is Production, set priority to High or Critical; the AI will also default to this
- **Drag & drop** — the file uploader accepts multiple files at once; hold Cmd/Ctrl to select several files
""")
