import os
import sys
from base64 import b64encode

import httpx
import pandas as pd
import streamlit as st

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from utils import ICON, page_setup
from dashboard.db import query, execute

st.set_page_config(page_title="Bug Tickets", page_icon=ICON, layout="wide")
page_setup()
st.title("Bug Tickets")


def _fetch_stack_traces(bug_id: str, failing_test_names: list) -> list[dict]:
    """Fetch stack traces for failing tests linked to this bug's run."""
    if not failing_test_names:
        return []
    placeholders = ",".join(["%s"] * len(failing_test_names))
    return query(f"""
        SELECT
            tc.name        AS test_name,
            tc.classname,
            tr.error_type,
            tr.error_message,
            tr.stack_trace,
            tr.status
        FROM test_results tr
        JOIN test_cases   tc  ON tc.id  = tr.case_id
        JOIN bugs          b  ON b.run_id = tr.run_id
        WHERE b.id::text = %s
          AND tc.name IN ({placeholders})
          AND tr.status IN ('failed','error')
        ORDER BY tc.name
    """, [bug_id] + list(failing_test_names))


def _build_jira_description(bug: dict, traces: list[dict]) -> list:
    """Build Atlassian Document Format content blocks."""
    def text_block(content: str) -> dict:
        return {
            "type": "paragraph",
            "content": [{"type": "text", "text": content}]
        }

    def heading_block(text: str, level: int = 3) -> dict:
        return {
            "type": "heading",
            "attrs": {"level": level},
            "content": [{"type": "text", "text": text}]
        }

    def code_block(code: str) -> dict:
        return {
            "type": "codeBlock",
            "attrs": {"language": "text"},
            "content": [{"type": "text", "text": code}]
        }

    content = [
        heading_block("Summary", 2),
        text_block(bug["summary"] or ""),
        heading_block("Root Cause Hypothesis", 2),
        text_block(bug["root_cause"] or ""),
        heading_block("Affected Feature", 2),
        text_block(bug["affected_feature"] or ""),
        heading_block("CI Context", 2),
        text_block(
            f"Branch: {bug['branch']}\n"
            f"Commit: {(bug['commit_sha'] or '')[:8]}\n"
            f"Run ID: {bug['github_run_id']}"
            + (f"\nPR: {bug['pr_title']}" if bug.get("pr_title") else "")
        ),
    ]

    if traces:
        content.append(heading_block("Failing Tests & Stack Traces", 2))
        for t in traces:
            content.append(heading_block(f"{t['test_name']}", 3))
            content.append(text_block(
                f"Class: {t['classname']}\n"
                f"Error Type: {t['error_type'] or 'N/A'}\n"
                f"Error Message: {t['error_message'] or 'N/A'}"
            ))
            if t.get("stack_trace"):
                content.append(code_block(t["stack_trace"][:3000]))
    elif bug.get("failing_test_ids"):
        content.append(heading_block("Failing Tests", 2))
        content.append(text_block("\n".join(f"• {t}" for t in bug["failing_test_ids"])))

    return content


def _push_to_jira(bug: dict, traces: list[dict]):
    jira_url = os.getenv("JIRA_BASE_URL", "").rstrip("/")
    jira_email = os.getenv("JIRA_EMAIL", "")
    jira_token = os.getenv("JIRA_API_TOKEN", "")
    project_key = os.getenv("JIRA_PROJECT_KEY", "SCRUM")

    if not all([jira_url, jira_email, jira_token]):
        st.error("Jira credentials not configured.")
        return

    token = b64encode(f"{jira_email}:{jira_token}".encode()).decode()
    headers = {"Authorization": f"Basic {token}", "Content-Type": "application/json"}
    priority_map = {"critical": "Highest", "high": "High", "medium": "Medium", "low": "Low"}

    payload = {
        "fields": {
            "project":     {"key": project_key},
            "summary":     bug["title"],
            "description": {
                "type": "doc",
                "version": 1,
                "content": _build_jira_description(bug, traces),
            },
            "issuetype": {"name": "Bug"},
            "priority":  {"name": priority_map.get(bug["severity"], "Medium")},
            "labels":    [
                (bug["affected_feature"] or "unknown").replace(" ", "_"),
                "automated-bug-agent",
                "ci-failure",
            ],
        }
    }

    try:
        with st.spinner("Creating Jira ticket..."):
            resp = httpx.post(
                f"{jira_url}/rest/api/3/issue",
                headers=headers,
                json=payload,
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
            ticket_key = data["key"]
            ticket_url = f"{jira_url}/browse/{ticket_key}"

        execute(
            "UPDATE bugs SET status='pushed', jira_ticket_key=%s, jira_ticket_url=%s WHERE id=%s",
            (ticket_key, ticket_url, str(bug["id"])),
        )
        st.success(f"Pushed to Jira: [{ticket_key}]({ticket_url})")
        st.rerun()
    except Exception as e:
        st.error(f"Failed to push to Jira: {e}")


# ── Draft Bugs ────────────────────────────────────────────────────────────────
tab_draft, tab_open = st.tabs(["Draft Bugs (Pending Review)", "Open Bugs (In Jira)"])

with tab_draft:
    st.markdown("Review AI-generated bug reports from CI failures and push them to Jira.")

    drafts = query("""
        SELECT
            b.id,
            b.title,
            b.summary,
            b.root_cause,
            b.affected_feature,
            b.severity,
            b.failing_test_ids,
            b.created_at,
            run.branch,
            run.commit_sha,
            run.github_run_id,
            run.pr_title
        FROM bugs b
        JOIN test_runs run ON run.id = b.run_id
        WHERE b.status = 'draft'
        ORDER BY
            CASE b.severity
                WHEN 'critical' THEN 1
                WHEN 'high'     THEN 2
                WHEN 'medium'   THEN 3
                ELSE 4
            END,
            b.created_at DESC
    """)

    if not drafts:
        st.success("No draft bugs. Everything looks clean!")
    else:
        for bug in drafts:
            severity_icon = {
                "critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢"
            }.get(bug["severity"], "⚪")

            with st.expander(
                f"{severity_icon} [{bug['severity'].upper()}] {bug['title']}",
                expanded=False,
            ):
                col1, col2 = st.columns([3, 1])

                # Fetch traces once per bug
                traces = _fetch_stack_traces(
                    str(bug["id"]), bug["failing_test_ids"] or []
                )

                with col1:
                    st.markdown(f"**Feature Area:** `{bug['affected_feature']}`")
                    st.markdown(f"**Branch:** `{bug['branch']}` | **Commit:** `{(bug['commit_sha'] or '')[:8]}`")
                    if bug["pr_title"]:
                        st.markdown(f"**PR:** {bug['pr_title']}")

                    st.markdown("**Summary:**")
                    st.info(bug["summary"])

                    st.markdown("**Root Cause Hypothesis:**")
                    st.warning(bug["root_cause"])

                    # Stack traces
                    if traces:
                        st.markdown("**Failing Tests & Stack Traces:**")
                        for t in traces:
                            with st.expander(f"`{t['test_name']}`", expanded=False):
                                st.markdown(f"**Class:** `{t['classname']}`")
                                st.markdown(f"**Error Type:** `{t['error_type'] or 'N/A'}`")
                                st.markdown(f"**Error Message:** {t['error_message'] or 'N/A'}")
                                if t.get("stack_trace"):
                                    st.code(t["stack_trace"], language="text")
                    else:
                        st.markdown("**Failing Tests:**")
                        for t in (bug["failing_test_ids"] or []):
                            st.markdown(f"- `{t}`")

                with col2:
                    st.markdown(f"**Detected:** {str(bug['created_at'])[:16]}")
                    st.markdown(f"**Run ID:** `{bug['github_run_id']}`")
                    st.markdown(f"**Traces attached:** {'Yes' if traces else 'No'}")

                    if st.button("Push to Jira", key=f"push_{bug['id']}", type="primary"):
                        _push_to_jira(bug, traces)

                    if st.button("Dismiss", key=f"dismiss_{bug['id']}"):
                        execute(
                            "UPDATE bugs SET status='wont_fix' WHERE id=%s",
                            (str(bug["id"]),),
                        )
                        st.rerun()

# ── Open Bugs ─────────────────────────────────────────────────────────────────
with tab_open:
    st.markdown("Bugs from CI that have been pushed to Jira.")

    open_bugs = query("""
        SELECT
            b.title,
            b.severity,
            b.affected_feature,
            b.jira_ticket_key,
            b.jira_ticket_url,
            b.status,
            b.created_at,
            run.branch
        FROM bugs b
        JOIN test_runs run ON run.id = b.run_id
        WHERE b.status IN ('pushed','open')
        ORDER BY b.created_at DESC
    """)

    if not open_bugs:
        st.info("No open bugs yet.")
    else:
        df = pd.DataFrame(open_bugs)
        df["Jira Ticket"] = df.apply(
            lambda r: f"[{r['jira_ticket_key']}]({r['jira_ticket_url']})"
            if r["jira_ticket_url"] else r["jira_ticket_key"] or "-",
            axis=1,
        )

        def _color_severity(val):
            return {
                "critical": "background-color:#FF4444;color:black;font-weight:bold",
                "high":     "background-color:#FF8C00;color:black;font-weight:bold",
                "medium":   "background-color:#FFD700;color:black;font-weight:bold",
                "low":      "background-color:#00CC44;color:black;font-weight:bold",
            }.get(val, "")

        display = df[["Jira Ticket","title","severity","affected_feature","branch","status","created_at"]].rename(columns={
            "title":"Title","severity":"Severity","affected_feature":"Feature",
            "branch":"Branch","status":"Status","created_at":"Created",
        })
        styled = display.style.map(_color_severity, subset=["Severity"])
        st.dataframe(styled, use_container_width=True, hide_index=True)
