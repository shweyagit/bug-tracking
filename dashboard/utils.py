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
    /* Hide User Manual from sidebar nav */
    [data-testid="stSidebarNav"] li:has(a[href*="User_Manual"]),
    [data-testid="stSidebarNav"] a[href*="User_Manual"] { display: none !important; }
    /* Top-right button bar */
    .topright-bar {
        position: fixed;
        top: 14px;
        right: 20px;
        z-index: 1000;
        display: flex;
        gap: 8px;
    }
    .topright-bar a {
        text-decoration: none;
        padding: 6px 14px;
        border-radius: 6px;
        font-size: 13px;
        font-weight: 600;
        background: rgba(255,255,255,0.08);
        border: 1px solid rgba(255,255,255,0.18);
        color: inherit;
        transition: background 0.15s;
    }
    .topright-bar a:hover { background: rgba(255,255,255,0.18); }
    </style>
    <div class="topright-bar">
        <a href="/7_User_Manual" target="_self">&#128196; User Manual</a>
    </div>
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
**SportIQ Bug Tracker**

Built by **Shweta Pandey**

An AI-powered bug tracking agent that integrates GitHub Actions, TestRail, Jira, and Claude AI to automate bug detection, reporting, and triage.

- GitHub: [@shwetapandey](https://github.com/shwetapandey)
            """)
