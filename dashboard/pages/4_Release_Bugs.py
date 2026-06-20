"""
Release Bug Tracker — enter a version label to see all bugs tagged for that release in Jira.
"""
import os
import sys
from base64 import b64encode

import httpx
import streamlit as st

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from utils import ICON, page_setup

st.set_page_config(page_title="Release Bugs", page_icon=ICON, layout="wide")
page_setup()

st.title("Release Bugs")
st.markdown("Enter a release version to see all Jira bugs tagged with that label.")

PRIORITY_COLOR = {
    "Highest": "#cf222e",
    "High":    "#bc4c00",
    "Medium":  "#9a6700",
    "Low":     "#1a7f37",
    "Lowest":  "#57606a",
}
PRIORITY_BG = {
    "Highest": "#fff0ee",
    "High":    "#fff3e0",
    "Medium":  "#fff8c5",
    "Low":     "#dafbe1",
    "Lowest":  "#f6f8fa",
}
STATUS_DONE = {"Done", "Resolved", "Closed", "Fixed"}


def _headers():
    auth = b64encode(
        f"{os.getenv('JIRA_EMAIL','')}:{os.getenv('JIRA_API_TOKEN','')}".encode()
    ).decode()
    return {"Authorization": f"Basic {auth}", "Accept": "application/json"}


@st.cache_data(ttl=60)
def fetch_release_bugs(project_key: str, version_label: str) -> list[dict]:
    jira_url = os.getenv("JIRA_BASE_URL", "").rstrip("/")
    if not jira_url or not version_label:
        return []
    jql = (
        f'project = {project_key} AND issuetype = Bug AND labels = "{version_label}"'
        f' ORDER BY priority ASC, created DESC'
    )
    try:
        resp = httpx.post(
            f"{jira_url}/rest/api/3/search/jql",
            headers={**_headers(), "Content-Type": "application/json"},
            json={
                "jql": jql,
                "maxResults": 200,
                "fields": ["summary", "status", "priority", "labels",
                           "assignee", "created", "updated"],
            },
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json().get("issues", [])
    except Exception as e:
        st.error(f"Failed to fetch from Jira: {e}")
        return []


def _pill(text, color, bg):
    return (
        f"<span style='background:{bg}; color:{color}; border:1px solid {color}44; "
        f"font-size:11px; font-weight:600; padding:2px 9px; border-radius:20px;'>{text}</span>"
    )


# ── Inputs ────────────────────────────────────────────────────────────────────
jira_url  = os.getenv("JIRA_BASE_URL", "").rstrip("/")
c1, c2, c3 = st.columns([2, 3, 1])
with c1:
    project_key = st.text_input("Project Key", value=os.getenv("JIRA_PROJECT_KEY", "SCRUM"))
with c2:
    version_label = st.text_input(
        "Release Version Label",
        placeholder="e.g. v1.2.0  (must match a Jira label exactly)",
    )
with c3:
    st.markdown("<br>", unsafe_allow_html=True)
    refresh = st.button("↺ Refresh", use_container_width=True)

if refresh:
    st.cache_data.clear()

if not version_label.strip():
    st.info("Enter a release version label to load bugs.")
    st.stop()

issues = fetch_release_bugs(project_key, version_label.strip())

if not issues:
    st.warning(f"No bugs found with label **{version_label}** in project **{project_key}**.")
    st.markdown(
        "Make sure bugs in Jira have this label set. "
        "You can add it via the bug detail page in Jira → Labels field."
    )
    st.stop()

# ── Summary metrics ───────────────────────────────────────────────────────────
fixed   = [i for i in issues if (i["fields"].get("status") or {}).get("name","") in STATUS_DONE]
open_   = [i for i in issues if i not in fixed]
pct     = int(len(fixed) / len(issues) * 100) if issues else 0

m1, m2, m3, m4 = st.columns(4)
m1.markdown(
    f"<div style='background:#e8f0fe; border:1px solid #0052cc33; border-radius:10px; "
    f"padding:14px; text-align:center;'>"
    f"<div style='color:#0052CC; font-size:10px; font-weight:700; letter-spacing:1px; text-transform:uppercase;'>Total Bugs</div>"
    f"<div style='color:#0052CC; font-size:28px; font-weight:800;'>{len(issues)}</div></div>",
    unsafe_allow_html=True,
)
m2.markdown(
    f"<div style='background:#fff0ee; border:1px solid #cf222e33; border-radius:10px; "
    f"padding:14px; text-align:center;'>"
    f"<div style='color:#cf222e; font-size:10px; font-weight:700; letter-spacing:1px; text-transform:uppercase;'>Still Open</div>"
    f"<div style='color:#cf222e; font-size:28px; font-weight:800;'>{len(open_)}</div></div>",
    unsafe_allow_html=True,
)
m3.markdown(
    f"<div style='background:#dafbe1; border:1px solid #1a7f3733; border-radius:10px; "
    f"padding:14px; text-align:center;'>"
    f"<div style='color:#1a7f37; font-size:10px; font-weight:700; letter-spacing:1px; text-transform:uppercase;'>Fixed</div>"
    f"<div style='color:#1a7f37; font-size:28px; font-weight:800;'>{len(fixed)}</div></div>",
    unsafe_allow_html=True,
)
m4.markdown(
    f"<div style='background:#f6f8fa; border:1px solid #d0d7de; border-radius:10px; "
    f"padding:14px; text-align:center;'>"
    f"<div style='color:#57606a; font-size:10px; font-weight:700; letter-spacing:1px; text-transform:uppercase;'>% Fixed</div>"
    f"<div style='color:#1f2328; font-size:28px; font-weight:800;'>{pct}%</div></div>",
    unsafe_allow_html=True,
)

st.markdown("<br>", unsafe_allow_html=True)

# ── Progress bar ──────────────────────────────────────────────────────────────
st.markdown(
    f"<div style='margin-bottom:4px; font-size:13px; color:#57606a;'>"
    f"Release readiness for <strong>{version_label}</strong></div>",
    unsafe_allow_html=True,
)
st.markdown(
    f"<div style='background:#d0d7de; border-radius:6px; height:10px; overflow:hidden;'>"
    f"<div style='background:#1a7f37; width:{pct}%; height:100%; border-radius:6px; "
    f"transition:width 0.4s;'></div></div>",
    unsafe_allow_html=True,
)
st.markdown("<br>", unsafe_allow_html=True)

# ── Bug list ──────────────────────────────────────────────────────────────────
tab_open, tab_fixed = st.tabs([f"Still Open ({len(open_)})", f"Fixed ({len(fixed)})"])

for tab, bug_list in [(tab_open, open_), (tab_fixed, fixed)]:
    with tab:
        if not bug_list:
            st.success("No bugs in this group.")
            continue
        for issue in bug_list:
            f = issue["fields"]
            key          = issue["key"]
            summary      = f.get("summary", "")
            priority_raw = (f.get("priority") or {}).get("name", "-")
            status_raw   = (f.get("status")   or {}).get("name", "-")
            assignee     = (f.get("assignee") or {}).get("displayName", "Unassigned")
            updated      = (f.get("updated") or "")[:10]
            border       = PRIORITY_COLOR.get(priority_raw, "#d0d7de")
            p_pill       = _pill(f"● {priority_raw}", PRIORITY_COLOR.get(priority_raw, "#57606a"),
                                 PRIORITY_BG.get(priority_raw, "#f6f8fa"))
            done         = status_raw in STATUS_DONE
            status_color = "#1a7f37" if done else "#0969da"
            status_bg    = "#dafbe1" if done else "#ddf4ff"
            s_pill       = _pill(status_raw, status_color, status_bg)

            st.markdown(
                f"<a href='{jira_url}/browse/{key}' target='_blank' style='text-decoration:none; color:inherit;'>"
                f"<div style='background:#fff; border:1px solid #d0d7de; border-left:4px solid {border}; "
                f"border-radius:8px; padding:12px 16px; margin-bottom:8px; "
                f"box-shadow:0 1px 3px rgba(0,0,0,0.05);'>"
                f"  <div style='display:flex; justify-content:space-between; align-items:flex-start; gap:12px;'>"
                f"    <div style='flex:1; min-width:0;'>"
                f"      <div style='display:flex; align-items:center; gap:8px; margin-bottom:4px;'>"
                f"        <span style='color:#0052CC; font-size:11px; font-weight:700; font-family:monospace;'>{key}</span>"
                f"        <span style='color:#1f2328; font-size:14px; font-weight:500; "
                f"                     overflow:hidden; text-overflow:ellipsis; white-space:nowrap;'>{summary}</span>"
                f"      </div>"
                f"      <span style='color:#656d76; font-size:11px;'>👤 {assignee} · ↻ {updated}</span>"
                f"    </div>"
                f"    <div style='display:flex; gap:6px; flex-shrink:0;'>{p_pill} {s_pill}</div>"
                f"  </div>"
                f"</div></a>",
                unsafe_allow_html=True,
            )
