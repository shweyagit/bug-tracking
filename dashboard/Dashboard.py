import streamlit as st

pg = st.navigation({
    "": [
        st.Page("dashboard/pages/Home.py",             title="Dashboard",       icon="🏠", default=True),
    ],
    "CI Dashboard": [
        st.Page("dashboard/pages/1_Test_Failures.py",  title="Test Failures",   icon="❌"),
        st.Page("dashboard/pages/2_Bug_Tickets.py",    title="CI Raised Bugs",  icon="🐛"),
        st.Page("dashboard/pages/3_Feature_Health.py", title="Feature Health",  icon="📊"),
    ],
    "Bug Reporting": [
        st.Page("dashboard/pages/5_Report_Bug.py",     title="Report Bug",      icon="📝"),
    ],
    "Tracking": [
        st.Page("dashboard/pages/4_Release_Bugs.py",   title="Release Bugs",    icon="🚀"),
        st.Page("dashboard/pages/6_Jira_Tracker.py",   title="Jira Tracker",    icon="🔗"),
        st.Page("dashboard/pages/_User_Manual.py",     title="User Manual",     icon="📖"),
    ],
})
pg.run()
