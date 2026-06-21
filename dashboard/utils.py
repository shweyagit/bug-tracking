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
