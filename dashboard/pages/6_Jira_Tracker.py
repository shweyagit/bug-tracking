"""
Live bug tracker — pulls open issues directly from Jira board.
"""
import os
import sys
from base64 import b64encode
import httpx
import plotly.express as px
import streamlit as st

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from utils import ICON, page_setup

st.set_page_config(page_title="Jira Bug Tracker", page_icon=ICON, layout="wide")
page_setup()

# ── Design tokens ─────────────────────────────────────────────────────────────
SURFACE       = "#ffffff"
SURFACE2      = "#f6f8fa"
BORDER        = "#d0d7de"
TEXT_PRIMARY  = "#1f2328"
TEXT_MUTED    = "#656d76"
JIRA_BLUE     = "#0052CC"

PRIORITY = {
    "Highest": {"color": "#cf222e", "bg": "#fff0ee", "label": "Critical", "dot": "●"},
    "High":    {"color": "#bc4c00", "bg": "#fff3e0", "label": "High",     "dot": "●"},
    "Medium":  {"color": "#9a6700", "bg": "#fff8c5", "label": "Medium",   "dot": "●"},
    "Low":     {"color": "#1a7f37", "bg": "#dafbe1", "label": "Low",      "dot": "●"},
    "Lowest":  {"color": "#57606a", "bg": "#f6f8fa", "label": "Lowest",   "dot": "●"},
}

STATUS = {
    "To Do":       {"color": "#57606a", "bg": "#f6f8fa"},
    "In Progress": {"color": "#0969da", "bg": "#ddf4ff"},
    "Done":        {"color": "#1a7f37", "bg": "#dafbe1"},
    "Blocked":     {"color": "#cf222e", "bg": "#fff0ee"},
    "In Review":   {"color": "#8250df", "bg": "#fbefff"},
}


def _headers() -> dict:
    auth = b64encode(f"{os.getenv('JIRA_EMAIL','')}:{os.getenv('JIRA_API_TOKEN','')}".encode()).decode()
    return {"Authorization": f"Basic {auth}", "Accept": "application/json"}


@st.cache_data(ttl=60)
def fetch_issues(project_key: str, status_filter: str) -> list[dict]:
    jira_url = os.getenv("JIRA_BASE_URL", "").rstrip("/")
    if not jira_url:
        return []
    status_jql = {
        "Open":        "statusCategory != Done",
        "In Progress": 'status = "In Progress"',
        "Done":        "statusCategory = Done",
        "All":         "",
    }.get(status_filter, "statusCategory != Done")
    jql = f"project = {project_key} AND issuetype = Bug"
    if status_jql:
        jql += f" AND {status_jql}"
    jql += " ORDER BY priority ASC, created DESC"
    try:
        resp = httpx.post(
            f"{jira_url}/rest/api/3/search/jql",
            headers={**_headers(), "Content-Type": "application/json"},
            json={"jql": jql, "maxResults": 100,
                  "fields": ["summary", "status", "priority", "labels",
                             "assignee", "created", "updated", "reporter"]},
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json().get("issues", [])
    except Exception as e:
        st.error(f"Failed to fetch from Jira: {e}")
        return []


def _pill(text: str, color: str, bg: str) -> str:
    return (f"<span style='background:{bg}; color:{color}; border:1px solid {color}55; "
            f"font-size:11px; font-weight:600; padding:2px 9px; border-radius:20px; "
            f"white-space:nowrap; letter-spacing:0.3px;'>{text}</span>")



# ── Page header ───────────────────────────────────────────────────────────────
st.markdown(f"""
<div style="display:flex; align-items:center; gap:14px; margin-bottom:20px;">
  <div style="background:{JIRA_BLUE}; border-radius:10px; width:44px; height:44px;
              display:flex; align-items:center; justify-content:center; flex-shrink:0;
              box-shadow:0 0 16px {JIRA_BLUE}66;">
    <svg width="24" height="24" viewBox="0 0 32 32" fill="none" xmlns="http://www.w3.org/2000/svg">
      <path d="M15.975 2L4 13.975l4.025 4.025L15.975 10.1l7.975 7.9 4.05-4.025L15.975 2z" fill="white"/>
      <path d="M15.975 19.9L8 27.875 12.025 32l3.95-3.95 3.975 3.95L24 27.875 15.975 19.9z" fill="white" opacity="0.65"/>
    </svg>
  </div>
  <div>
    <h1 style="margin:0; font-size:24px; font-weight:700; color:{TEXT_PRIMARY}; line-height:1.2;">Live Bug Tracker</h1>
    <p style="margin:0; color:{TEXT_MUTED}; font-size:13px;">Synced live from Jira · bugs only</p>
  </div>
</div>
""", unsafe_allow_html=True)

# ── Filters ───────────────────────────────────────────────────────────────────
c1, c2, c3, c4 = st.columns([2, 2, 3, 1])
with c1:
    project_key = st.text_input("Project Key", value=os.getenv("JIRA_PROJECT_KEY", "SCRUM"), label_visibility="collapsed")
with c2:
    status_filter = st.selectbox("Status", ["Open", "In Progress", "Done", "All"], label_visibility="collapsed")
with c3:
    search_text = st.text_input("Search", placeholder="Search by title, key or label...", label_visibility="collapsed")
with c4:
    if st.button("↺ Refresh", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

issues = fetch_issues(project_key, status_filter)
if not issues:
    st.info("No bugs found.")
    st.stop()

jira_url = os.getenv("JIRA_BASE_URL", "").rstrip("/")

# ── Metric strip ──────────────────────────────────────────────────────────────
pcounts: dict[str, int] = {}
for issue in issues:
    p = (issue["fields"].get("priority") or {}).get("name", "None")
    pcounts[p] = pcounts.get(p, 0) + 1

metrics = [
    ("Total",    len(issues),               "#0052CC", "#e8f0fe"),
    ("Critical", pcounts.get("Highest", 0), "#cf222e", "#fff0ee"),
    ("High",     pcounts.get("High", 0),    "#bc4c00", "#fff3e0"),
    ("Medium",   pcounts.get("Medium", 0),  "#9a6700", "#fff8c5"),
    ("Low",      pcounts.get("Low", 0),     "#1a7f37", "#dafbe1"),
]
cols = st.columns(5)
for col, (label, val, color, bg) in zip(cols, metrics):
    col.markdown(
        f"<div style='background:{bg}; border:1px solid {color}33; border-radius:10px; "
        f"padding:14px 12px 12px; text-align:center;'>"
        f"<div style='color:{color}; font-size:10px; font-weight:700; letter-spacing:1px; "
        f"text-transform:uppercase; margin-bottom:6px;'>{label}</div>"
        f"<div style='color:{color}; font-size:30px; font-weight:800; line-height:1;'>{val}</div>"
        f"</div>",
        unsafe_allow_html=True,
    )
st.markdown("<div style='height:20px'></div>", unsafe_allow_html=True)

# ── Status bar chart ──────────────────────────────────────────────────────────
status_counts: dict[str, int] = {}
for issue in issues:
    s = (issue["fields"].get("status") or {}).get("name", "Unknown")
    status_counts[s] = status_counts.get(s, 0) + 1

status_color_map = {
    "To Do":       "#57606a",
    "In Progress": "#0969da",
    "Done":        "#1a7f37",
    "Blocked":     "#cf222e",
    "In Review":   "#8250df",
}
chart_data = {
    "Status": list(status_counts.keys()),
    "Count":  list(status_counts.values()),
    "Color":  [status_color_map.get(s, "#57606a") for s in status_counts.keys()],
}
fig = px.bar(
    chart_data, x="Status", y="Count", color="Status",
    color_discrete_map={s: status_color_map.get(s, "#57606a") for s in status_counts},
    text="Count",
)
fig.update_traces(textposition="outside")
fig.update_layout(
    showlegend=False,
    plot_bgcolor="white",
    paper_bgcolor="white",
    margin=dict(t=10, b=10, l=0, r=0),
    height=220,
    xaxis=dict(title="", tickfont=dict(size=12)),
    yaxis=dict(title="", showgrid=True, gridcolor="#f0f0f0"),
)
st.plotly_chart(fig, use_container_width=True)

# ── Priority filter tabs ───────────────────────────────────────────────────────
pf_options = ["All"] + [f"{PRIORITY[k]['dot']} {PRIORITY[k]['label']}"
                         for k in PRIORITY if pcounts.get(k, 0) > 0]
selected_p = st.radio("Priority", pf_options, horizontal=True, index=0)

# ── Bug cards ─────────────────────────────────────────────────────────────────
shown = 0
for issue in issues:
    f = issue["fields"]
    key          = issue["key"]
    priority_raw = (f.get("priority") or {}).get("name", "-")
    status_raw   = (f.get("status")   or {}).get("name", "-")
    summary      = f.get("summary", "")
    labels       = f.get("labels") or []
    assignee     = (f.get("assignee") or {}).get("displayName", "Unassigned")
    updated      = (f.get("updated") or "")[:10]

    pcfg = PRIORITY.get(priority_raw, {"color": "#6e7681", "bg": "#1c2128", "label": priority_raw, "dot": "●"})
    scfg = STATUS.get(status_raw, {"color": "#6e7681", "bg": "#21262d"})
    p_display = f"{pcfg['dot']} {pcfg['label']}"

    if search_text:
        term = search_text.lower()
        if not (term in summary.lower() or term in key.lower() or
                any(term in lb.lower() for lb in labels)):
            continue
    if selected_p and selected_p != "All" and p_display != selected_p:
        continue

    shown += 1
    label_html = " ".join(
        f"<span style='background:#f6f8fa; color:#57606a; border:1px solid #d0d7de; "
        f"font-size:10px; padding:1px 7px; border-radius:20px;'>{lb}</span>"
        for lb in labels
    )
    priority_pill = _pill(p_display, pcfg["color"], pcfg["bg"])
    status_pill   = _pill(status_raw, scfg["color"], scfg["bg"])

    st.markdown(
        f"<a href='{jira_url}/browse/{key}' target='_blank' style='text-decoration:none; color:inherit;'>"
        f"<div style='background:{SURFACE}; border:1px solid {BORDER}; border-left:4px solid {pcfg['color']}; "
        f"border-radius:8px; padding:14px 18px; margin-bottom:8px; "
        f"box-shadow:0 1px 3px rgba(0,0,0,0.06);'>"
        f"  <div style='display:flex; align-items:flex-start; justify-content:space-between; gap:12px;'>"
        f"    <div style='flex:1; min-width:0;'>"
        f"      <div style='display:flex; align-items:center; gap:8px; margin-bottom:5px;'>"
        f"        <span style='color:{JIRA_BLUE}; font-size:11px; font-weight:700; "
        f"                     font-family:monospace; white-space:nowrap;'>{key}</span>"
        f"        <span style='color:{TEXT_PRIMARY}; font-size:14px; font-weight:500; "
        f"                     overflow:hidden; text-overflow:ellipsis; white-space:nowrap;'>{summary}</span>"
        f"      </div>"
        f"      <div style='display:flex; align-items:center; gap:10px; flex-wrap:wrap;'>"
        f"        <span style='color:{TEXT_MUTED}; font-size:11px;'>👤 {assignee}</span>"
        f"        <span style='color:{TEXT_MUTED}; font-size:11px;'>↻ {updated}</span>"
        f"        {label_html}"
        f"      </div>"
        f"    </div>"
        f"    <div style='display:flex; gap:6px; flex-shrink:0; align-items:flex-start;'>"
        f"      {priority_pill} {status_pill}"
        f"    </div>"
        f"  </div>"
        f"</div></a>",
        unsafe_allow_html=True,
    )

if shown == 0:
    st.info("No bugs match your filters.")

# ── Detail view ───────────────────────────────────────────────────────────────
st.divider()
st.markdown(f"<h3 style='color:{TEXT_PRIMARY};'>Bug Detail</h3>", unsafe_allow_html=True)

selected_key = st.selectbox("Select bug to inspect", [i["key"] for i in issues])

if selected_key:
    selected = next((i for i in issues if i["key"] == selected_key), None)
    if selected:
        f = selected["fields"]
        priority_raw = (f.get("priority") or {}).get("name", "-")
        status_raw   = (f.get("status")   or {}).get("name", "-")
        pcfg = PRIORITY.get(priority_raw, {"color": "#6e7681", "bg": "#1c2128", "label": priority_raw, "dot": "●"})
        scfg = STATUS.get(status_raw, {"color": "#6e7681", "bg": "#21262d"})

        col_a, col_b = st.columns([2, 1])
        with col_a:
            st.markdown(f"### {f['summary']}")
            desc = f.get("description")
            if desc:
                for block in desc.get("content", []):
                    for inline in block.get("content", []):
                        if inline.get("type") == "text":
                            st.markdown(inline["text"])
            else:
                st.info("No description.")

        with col_b:
            p_pill = _pill(f"{pcfg['dot']} {pcfg['label']}", pcfg["color"], pcfg["bg"])
            s_pill = _pill(status_raw, scfg["color"], scfg["bg"])
            st.markdown(
                f"<div style='background:{SURFACE2}; border:1px solid {pcfg['color']}55; "
                f"border-left:4px solid {pcfg['color']}; border-radius:8px; padding:16px;'>"
                f"<p style='margin:0 0 10px;'><span style='color:{TEXT_MUTED}; font-size:11px;'>KEY</span><br>"
                f"  <a href='{jira_url}/browse/{selected_key}' target='_blank' "
                f"     style='color:{JIRA_BLUE}; font-weight:700; font-family:monospace;'>{selected_key}</a></p>"
                f"<p style='margin:0 0 10px;'><span style='color:{TEXT_MUTED}; font-size:11px;'>PRIORITY</span><br>{p_pill}</p>"
                f"<p style='margin:0 0 10px;'><span style='color:{TEXT_MUTED}; font-size:11px;'>STATUS</span><br>{s_pill}</p>"
                f"<p style='margin:0 0 10px;'><span style='color:{TEXT_MUTED}; font-size:11px;'>ASSIGNEE</span><br>"
                f"  <span style='color:{TEXT_PRIMARY};'>{(f.get('assignee') or {}).get('displayName', 'Unassigned')}</span></p>"
                f"<p style='margin:0 0 10px;'><span style='color:{TEXT_MUTED}; font-size:11px;'>REPORTER</span><br>"
                f"  <span style='color:{TEXT_PRIMARY};'>{(f.get('reporter') or {}).get('displayName', '-')}</span></p>"
                f"<p style='margin:0 0 10px;'><span style='color:{TEXT_MUTED}; font-size:11px;'>LABELS</span><br>"
                f"  <span style='color:{TEXT_PRIMARY};'>{', '.join(f.get('labels') or []) or '-'}</span></p>"
                f"<p style='margin:0 0 10px;'><span style='color:{TEXT_MUTED}; font-size:11px;'>CREATED</span><br>"
                f"  <span style='color:{TEXT_PRIMARY};'>{(f.get('created') or '')[:10]}</span></p>"
                f"<p style='margin:0;'><span style='color:{TEXT_MUTED}; font-size:11px;'>UPDATED</span><br>"
                f"  <span style='color:{TEXT_PRIMARY};'>{(f.get('updated') or '')[:10]}</span></p>"
                f"</div>",
                unsafe_allow_html=True,
            )
