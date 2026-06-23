import streamlit as st

pg = st.navigation({
    "": [
        st.Page("pages/Home.py",             title="Home",            icon="🏠", default=True),
    ],
    "CI Dashboard": [
        st.Page("pages/1_Test_Failures.py",  title="Test Failures",   icon="❌"),
        st.Page("pages/2_Bug_Tickets.py",    title="CI Raised Bugs",  icon="🐛"),
        st.Page("pages/3_Feature_Health.py", title="Feature Health",  icon="📊"),
    ],
    "Bug Reporting": [
        st.Page("pages/5_Report_Bug.py",     title="Report Bug",      icon="📝"),
    ],
    "Tracking": [
        st.Page("pages/4_Release_Bugs.py",   title="Release Bugs",    icon="🚀"),
        st.Page("pages/6_Jira_Tracker.py",   title="Jira Tracker",    icon="🔗"),
    ],
})
pg.run()
