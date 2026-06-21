import streamlit as st
from utils import ICON, page_setup

st.set_page_config(
    page_title="Bug Tracking Agent",
    page_icon=ICON,
    layout="wide",
    initial_sidebar_state="expanded",
)
page_setup()

st.title("Bug Tracking Agent")
st.markdown(
    """
    Enterprise bug intelligence powered by GitHub Actions, TestRail, Jira, and Claude AI.

    Use the sidebar to navigate:
    - **Test Failures** — Latest CI run failures with AI analysis
    - **Bug Tickets** — Draft and open bug tickets
    - **Feature Health** — Which features fail most frequently
    - **Release Bugs** — Bugs open at release time
    """
)

# Quick stats
import psycopg2
import os

DB_URL = os.getenv("DATABASE_URL", "").replace("postgresql+asyncpg://", "postgresql://")


@st.cache_data(ttl=60)
def get_summary_stats():
    try:
        conn = psycopg2.connect(DB_URL)
        cur = conn.cursor()

        cur.execute("SELECT COUNT(*) FROM bugs WHERE status = 'draft'")
        drafts = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM bugs WHERE status IN ('open', 'pushed')")
        open_bugs = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM test_runs WHERE conclusion = 'failure'")
        failed_runs = cur.fetchone()[0]

        cur.execute(
            "SELECT COUNT(*) FROM test_results WHERE status IN ('failed','error') "
            "AND created_at > NOW() - INTERVAL '7 days'"
        )
        recent_failures = cur.fetchone()[0]

        cur.close()
        conn.close()
        return drafts, open_bugs, failed_runs, recent_failures
    except Exception:
        return 0, 0, 0, 0


drafts, open_bugs, failed_runs, recent_failures = get_summary_stats()

col1, col2, col3, col4 = st.columns(4)
col1.metric("Draft Bugs", drafts, help="AI-generated bug reports awaiting review")
col2.metric("Open Bugs", open_bugs, help="Bugs pushed to Jira and still open")
col3.metric("Failed Runs (All Time)", failed_runs)
col4.metric("Test Failures (Last 7 Days)", recent_failures)

if all(v == 0 for v in [drafts, open_bugs, failed_runs, recent_failures]):
    st.info(
        "No data yet — this is normal on first run.\n\n"
        "**To get started:**\n"
        "- Go to **Report Bug** to manually file a bug and push it to Jira\n"
        "- Connect your GitHub Actions to the webhook to auto-capture CI failures\n"
        "- Use **Jira Tracker** to browse existing bugs from your Jira board"
    )
