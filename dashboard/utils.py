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
            st.markdown("""
**About This App**

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
                st.markdown("""
#### Getting Started
Start the full stack with:
```bash
./start.sh
```
This starts the dashboard at **http://localhost:8501**, the local verify agent on port 8502, and an ngrok tunnel.
Check the sidebar — **Local Agent** should show 🟢 connected.

---

#### Reporting a UI Bug
1. Go to **Report Bug → UI Bug tab**
2. Click **Record Steps** — a browser opens, reproduce the bug, then close it
3. Click **Finish Recording** — the agent converts your actions into steps and captures a Playwright trace
4. Describe the bug, add attachments, then click **Draft Bug Ticket**
5. Review the AI-generated draft and click **Push to Jira**

---

#### Reporting an API Bug
**Option A — Manual:** Go to **Report Bug → API Bug tab**, fill in the endpoint, request/response details, and click **Draft Bug Ticket**.

**Option B — Newman (recommended):** Click **Run API Tests** — the agent runs the full test suite, any failure appears as a card. Click **Draft** to auto-fill the form.

---

#### Dashboard Pages
| Page | Description |
|------|-------------|
| Test Failures | CI failures from GitHub Actions with AI analysis |
| Bug Tickets | Draft and open bug tickets |
| Feature Health | Which features fail most frequently |
| Release Bugs | Bugs open at each release gate |
| Report Bug | File a UI or API bug manually |
| Jira Tracker | Browse bugs on your Jira board |

---

#### Tips
- Download `playwright_trace.zip` from Jira and open it at [trace.playwright.dev](https://trace.playwright.dev) to replay every click
- Record only the steps needed to trigger the bug
- If environment is Production, set priority to High or Critical
                """)
