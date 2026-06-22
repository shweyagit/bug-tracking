"""
Shared page setup — call after st.set_page_config() on every page.
"""
import base64
import os
from pathlib import Path

import httpx
import streamlit as st

ASSETS = Path(__file__).parent / "assets"
LOGO   = str(ASSETS / "logo.png")
ICON   = str(ASSETS / "favicon.png")


@st.cache_data
def _favicon_b64() -> str:
    return base64.b64encode((ASSETS / "favicon.png").read_bytes()).decode()


@st.cache_data(ttl=15)
def _agent_status() -> bool:
    try:
        r = httpx.get(
            f"{os.getenv('VERIFY_SERVICE_URL', 'http://host.docker.internal:8502')}/health",
            timeout=2,
        )
        return r.status_code == 200
    except Exception:
        return False


def page_setup():
    st.markdown("""
    <style>
    /* Lift branding above nav */
    [data-testid="stSidebarContent"] { display: flex !important; flex-direction: column !important; }
    [data-testid="stSidebarUserContent"] { order: -1 !important; padding-bottom: 0 !important; }
    [data-testid="stSidebarNav"] { padding-top: 0 !important; margin-top: 0 !important; }
    /* Hide the collapse/close button — covers multiple Streamlit versions */
    [data-testid="stSidebarCollapseButton"],
    [data-testid="stSidebarCollapsedControl"],
    [data-testid="collapsedControl"],
    button[aria-label="Close sidebar"],
    section[data-testid="stSidebar"] > div:first-child > button { display: none !important; }
    /* Hide three-dot toolbar menu */
    [data-testid="stToolbar"],
    #MainMenu { visibility: hidden !important; display: none !important; }
    </style>
    """, unsafe_allow_html=True)

    with st.sidebar:
        st.markdown(
            f"<div style='display:flex; align-items:center; gap:12px; padding:8px 0 4px 0;'>"
            f"<img src='data:image/png;base64,{_favicon_b64()}' width='44' style='border-radius:8px;'/>"
            f"<span style='font-size:17px; font-weight:800; line-height:1.25; color:inherit;'>"
            f"SportIQ<br>Bug Tracker</span>"
            f"</div>",
            unsafe_allow_html=True,
        )
        st.markdown("---")

        # Local agent status — inline, after Your Name, before nav links
        if _agent_status():
            st.markdown("🟢 **Local Agent** connected")
        else:
            st.markdown("🔴 **Local Agent** offline")
            st.caption("Run `python verify_service.py` to enable recording.")

    # About Me popover — top-right, rendered after sidebar
    col_spacer, col_btn = st.columns([0.85, 0.15])
    with col_btn:
        with st.popover("About Me", use_container_width=True):
            with st.expander("About This App"):
                st.markdown("""
**SportIQ Bug Tracker** is an AI-powered bug tracking agent built for the SportIQ platform.

It automatically detects, analyses, and files bug reports by connecting:
- **GitHub Actions** — captures CI test failures in real time
- **TestRail** — syncs test results and run history
- **Jira** — creates and tracks bug tickets automatically
- **Claude AI** — analyses failures, writes reproduction steps, and prioritises bugs

You can also manually report UI bugs (with Playwright browser recording) or API bugs (with Newman test runs), and Claude will draft the full Jira ticket for you.

Built by **Shweta Pandey**
                """)

            with st.expander("User Manual"):
                st.markdown("#### Getting Started")
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

                st.markdown("#### Reporting a UI Bug")
                st.markdown("""
**Step 1 — Record the bug**

Go to **Report Bug → UI Bug tab**. Open **Record reproduction steps** and click **Record Steps**.
A browser opens — navigate to the app and reproduce the bug exactly as a user would. Close the browser when done.

Click **Finish Recording**. The agent will:
- Convert your actions into numbered natural language steps
- Replay them headlessly to capture a **Playwright trace**

The trace is attached to the Jira ticket automatically.

**Step 2 — Draft the ticket**

Review the recorded steps — edit or remove any captured incorrectly.
Describe the bug in plain English in the **Describe the bug** field (required).
Add supporting files via the drag & drop uploader. Enter your name, then click **Draft Bug Ticket**.

Claude AI will structure the report into a clear title, numbered steps, expected vs actual behaviour, priority, labels, and affected feature.

**Step 3 — Review & Push**

Review the AI-generated draft, edit any field, then click **Push to Jira**. The ticket is created with the Playwright trace and attachments included.
                """)

                st.markdown("#### Reporting an API Bug")
                st.markdown("""
**Option A — Manual entry**

Go to **Report Bug → API Bug tab**. Fill in environment, method, endpoint, request body, response status, response body, and any additional context. Click **Draft Bug Ticket** — AI formats the ticket with curl-reproducible steps, then push to Jira.

**Option B — Run API Tests (recommended)**

Open **Run API tests — auto-detect failures** and click **Run API Tests**.
The agent runs the full SportIQ API test suite via Newman (~2 minutes).
Any failing request appears as a card. Click **Draft** on any failure — the form auto-fills with all evidence. Click **Draft Bug Ticket** → review → **Push to Jira**.
                """)

                st.markdown("#### Dashboard Pages")
                st.markdown("""
| Page | Description |
|------|-------------|
| Test Failures | CI failures from GitHub Actions with AI root-cause analysis |
| Bug Tickets | Draft and open bug tickets awaiting review |
| Feature Health | Which features fail most frequently across all test runs |
| Release Bugs | Bugs that were open at the time of each release |
| Report Bug | File a new UI or API bug manually |
| Jira Tracker | Browse bugs already pushed to your Jira board |
                """)

                st.markdown("#### Tips")
                st.markdown("""
- **Playwright trace** — download `playwright_trace.zip` from the Jira ticket and open it at [trace.playwright.dev](https://trace.playwright.dev) to replay every click, see network calls, and inspect console errors
- **Newman tests** — the collection file `SportIQ_API.postman_collection.json` is in the project root; import it into Postman to run or edit individual tests
- **Recording tips** — record only the steps needed to trigger the bug; avoid clicking around after the bug appears
- **API bug priority** — if environment is Production, set priority to High or Critical
- **Drag & drop** — the file uploader accepts multiple files at once; hold Cmd/Ctrl to select several
                """)
