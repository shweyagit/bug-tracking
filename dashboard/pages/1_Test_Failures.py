import streamlit as st
import pandas as pd

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from utils import ICON, page_setup
from dashboard.db import query

st.set_page_config(page_title="Test Failures", page_icon=ICON, layout="wide")
page_setup()
st.title("Test Failures")

# Filters
col1, col2, col3 = st.columns(3)
with col1:
    branch_filter = st.text_input("Branch", placeholder="main")
with col2:
    feature_filter = st.text_input("Feature Area", placeholder="auth")
with col3:
    limit = st.slider("Max results", 20, 200, 50)

# Build query
conditions = ["tr.status IN ('failed','error')"]
params = []
if branch_filter:
    conditions.append("run.branch = %s")
    params.append(branch_filter)
if feature_filter:
    conditions.append("tc.feature_area ILIKE %s")
    params.append(f"%{feature_filter}%")
params.append(limit)

sql = f"""
SELECT
    run.branch,
    run.commit_sha,
    run.pr_title,
    run.completed_at,
    tc.name        AS test_name,
    tc.classname,
    tc.feature_area,
    tr.status,
    tr.error_message,
    tr.error_type,
    tr.duration_seconds,
    fs.consecutive_failures,
    fs.failure_count,
    fs.total_runs
FROM test_results tr
JOIN test_runs   run ON run.id = tr.run_id
JOIN test_cases  tc  ON tc.id  = tr.case_id
LEFT JOIN failure_stats fs ON fs.case_id = tc.id
WHERE {" AND ".join(conditions)}
ORDER BY run.completed_at DESC
LIMIT %s
"""

try:
    rows = query(sql, params)
except Exception as e:
    st.error(f"DB error: {e}")
    st.stop()

if not rows:
    st.info("No failures found. Either all tests pass or no runs have been processed yet.")
    st.stop()

df = pd.DataFrame(rows)

# Summary
total = len(df)
features = df["feature_area"].nunique()
st.markdown(f"**{total} failures** across **{features} feature areas**")

# Table
st.dataframe(
    df[[
        "completed_at", "branch", "feature_area", "test_name",
        "status", "error_type", "error_message",
        "consecutive_failures", "failure_count", "total_runs"
    ]].rename(columns={
        "completed_at": "Run Time",
        "branch": "Branch",
        "feature_area": "Feature",
        "test_name": "Test",
        "status": "Status",
        "error_type": "Error Type",
        "error_message": "Error Message",
        "consecutive_failures": "Consecutive Fails",
        "failure_count": "Total Fails",
        "total_runs": "Total Runs",
    }),
    use_container_width=True,
    hide_index=True,
)

# Detail expander
st.subheader("Full Error Details")
selected_test = st.selectbox("Select a test to inspect", df["test_name"].unique())
row = df[df["test_name"] == selected_test].iloc[0]
st.markdown(f"**Class:** `{row['classname']}`")
st.markdown(f"**Feature Area:** `{row['feature_area']}`")
st.markdown(f"**Error Type:** `{row['error_type']}`")
st.markdown(f"**Error Message:**")
st.code(row["error_message"] or "N/A", language="text")
