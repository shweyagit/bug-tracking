import os
import sys

import pandas as pd
import plotly.express as px
import streamlit as st

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from utils import ICON, page_setup
from dashboard.db import query

st.set_page_config(page_title="Feature Health", page_icon=ICON, layout="wide")
page_setup()
st.title("Feature Health")
st.markdown("Track which features fail most frequently across CI runs.")

# ── Failure Rate by Feature ───────────────────────────────────────────────────
feature_stats = query("""
    SELECT
        fs.feature_area,
        SUM(fs.failure_count)                              AS total_failures,
        SUM(fs.total_runs)                                 AS total_runs,
        ROUND(
            100.0 * SUM(fs.failure_count) / NULLIF(SUM(fs.total_runs), 0), 1
        )                                                  AS failure_rate_pct,
        MAX(fs.last_failed_at)                             AS last_failed_at,
        MAX(fs.consecutive_failures)                       AS max_consecutive_failures,
        COUNT(DISTINCT fs.case_id)                         AS test_count
    FROM failure_stats fs
    GROUP BY fs.feature_area
    ORDER BY total_failures DESC
""")

if not feature_stats:
    st.info("No data yet. Process some workflow runs first.")
    st.stop()

df = pd.DataFrame(feature_stats)

col1, col2 = st.columns(2)

with col1:
    st.subheader("Failure Count by Feature")
    fig = px.bar(
        df.head(20),
        x="feature_area",
        y="total_failures",
        color="failure_rate_pct",
        color_continuous_scale="RdYlGn_r",
        labels={"feature_area": "Feature", "total_failures": "Failures", "failure_rate_pct": "Failure Rate %"},
    )
    fig.update_layout(xaxis_tickangle=-45)
    st.plotly_chart(fig, use_container_width=True)

with col2:
    st.subheader("Failure Rate % by Feature")
    fig2 = px.bar(
        df.head(20).sort_values("failure_rate_pct", ascending=False),
        x="feature_area",
        y="failure_rate_pct",
        color="failure_rate_pct",
        color_continuous_scale="RdYlGn_r",
        labels={"feature_area": "Feature", "failure_rate_pct": "Failure Rate %"},
    )
    fig2.update_layout(xaxis_tickangle=-45)
    st.plotly_chart(fig2, use_container_width=True)

# ── Summary Table ─────────────────────────────────────────────────────────────
st.subheader("Feature Summary Table")
st.dataframe(
    df.rename(columns={
        "feature_area": "Feature",
        "total_failures": "Total Failures",
        "total_runs": "Total Runs",
        "failure_rate_pct": "Failure Rate %",
        "last_failed_at": "Last Failed",
        "max_consecutive_failures": "Max Consecutive Fails",
        "test_count": "Test Count",
    }),
    use_container_width=True,
    hide_index=True,
)

# ── Most Flaky Tests ──────────────────────────────────────────────────────────
st.subheader("Most Frequently Failing Tests")
selected_feature = st.selectbox(
    "Filter by feature area",
    ["All"] + sorted(df["feature_area"].dropna().unique().tolist()),
)

params = []
where = ""
if selected_feature != "All":
    where = "WHERE fs.feature_area = %s"
    params.append(selected_feature)

flaky_tests = query(f"""
    SELECT
        tc.name                    AS test_name,
        tc.classname,
        fs.feature_area,
        fs.failure_count,
        fs.total_runs,
        ROUND(100.0 * fs.failure_count / NULLIF(fs.total_runs, 0), 1) AS failure_rate_pct,
        fs.consecutive_failures,
        fs.last_failed_at
    FROM failure_stats fs
    JOIN test_cases tc ON tc.id = fs.case_id
    {where}
    ORDER BY fs.failure_count DESC
    LIMIT 50
""", params or None)

if flaky_tests:
    st.dataframe(
        pd.DataFrame(flaky_tests).rename(columns={
            "test_name": "Test",
            "classname": "Class",
            "feature_area": "Feature",
            "failure_count": "Failures",
            "total_runs": "Runs",
            "failure_rate_pct": "Failure Rate %",
            "consecutive_failures": "Consecutive Fails",
            "last_failed_at": "Last Failed",
        }),
        use_container_width=True,
        hide_index=True,
    )

# ── Failure Trend Over Time ───────────────────────────────────────────────────
st.subheader("Failure Trend — Last 30 Days")
trend = query("""
    SELECT
        DATE(run.completed_at)  AS run_date,
        tc.feature_area,
        COUNT(*)                AS failure_count
    FROM test_results tr
    JOIN test_runs run ON run.id = tr.run_id
    JOIN test_cases tc  ON tc.id  = tr.case_id
    WHERE tr.status IN ('failed','error')
      AND run.completed_at > NOW() - INTERVAL '30 days'
    GROUP BY DATE(run.completed_at), tc.feature_area
    ORDER BY run_date
""")

if trend:
    trend_df = pd.DataFrame(trend)
    fig3 = px.line(
        trend_df,
        x="run_date",
        y="failure_count",
        color="feature_area",
        labels={"run_date": "Date", "failure_count": "Failures", "feature_area": "Feature"},
    )
    st.plotly_chart(fig3, use_container_width=True)
