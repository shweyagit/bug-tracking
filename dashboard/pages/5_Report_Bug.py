"""
Manual bug reporting page.
User writes in plain English → AI structures it → user reviews → push to Jira.
"""
import base64
import json
import os
import sys
from base64 import b64encode

import anthropic
import httpx
import streamlit as st

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from utils import ICON, page_setup

st.set_page_config(page_title="Report a Bug", page_icon=ICON, layout="wide")
page_setup()


def _verify_bug_on_app(bug: dict):
    steps = bug.get("steps_to_reproduce", [])
    if not steps:
        st.warning("No steps to reproduce found. Generate the bug report first.")
        return

    verify_url = os.getenv("VERIFY_SERVICE_URL", "http://host.docker.internal:8502")

    with st.spinner("Opening browser on your machine and reproducing the bug... this may take a minute."):
        try:
            resp = httpx.post(
                f"{verify_url}/verify",
                json={"steps": steps, "description": bug.get("description", "")},
                timeout=300,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            st.error(f"Verification service not reachable: {e}\n\nMake sure you have started it with:\n```\npython verify_service.py\n```")
            return

    # Convert response into session state format
    class _Step:
        def __init__(self, d):
            self.step_number = d["step_number"]
            self.step_description = d["step_description"]
            self.action_taken = d["action_taken"]
            self.screenshot_b64 = d["screenshot_b64"]
            self.success = d["success"]
            self.observation = d["observation"]

    class _Result:
        def __init__(self, d):
            self.bug_confirmed = d["bug_confirmed"]
            self.confidence = d["confidence"]
            self.summary = d["summary"]
            self.steps = [_Step(s) for s in d["steps"]]
            self.console_errors = d["console_errors"]
            self.failing_step = d["failing_step"]
            self.reproduction_url = d["reproduction_url"]

    result = _Result(data)
    st.session_state["verification_result"] = result

    auto_attachments = []
    for step in result.steps:
        if step.screenshot_b64:
            img_bytes = base64.b64decode(step.screenshot_b64)
            auto_attachments.append({
                "name": f"step_{step.step_number}.png",
                "bytes": img_bytes,
                "type": "image/png",
            })
    st.session_state["auto_screenshots"] = auto_attachments


def _show_verification_result(result):
    st.divider()
    st.subheader("Verification Result")

    if result.bug_confirmed:
        st.error(f"Bug Confirmed ({result.confidence} confidence)")
    else:
        st.success(f"Bug NOT reproduced ({result.confidence} confidence)")

    st.markdown(f"**Summary:** {result.summary}")
    if result.reproduction_url:
        st.markdown(f"**Failed at URL:** `{result.reproduction_url}`")
    if result.failing_step:
        st.markdown(f"**Bug appeared at step:** {result.failing_step}")
    if result.console_errors:
        with st.expander("Console Errors"):
            for err in result.console_errors:
                st.code(err, language="text")

    st.markdown("**Step-by-step screenshots:**")
    for step in result.steps:
        status = "✅" if step.success else "❌"
        with st.expander(f"{status} Step {step.step_number}: {step.step_description}"):
            st.markdown(f"**Action:** {step.action_taken}")
            st.markdown(f"**Observation:** {step.observation}")
            import base64
            if step.screenshot_b64:
                try:
                    img_bytes = base64.b64decode(step.screenshot_b64)
                    st.image(img_bytes, width=900)
                except Exception:
                    st.warning("Screenshot not available for this step.")


def _push_manual_bug_to_jira(bug: dict, attachments: list):
    jira_url = os.getenv("JIRA_BASE_URL", "").rstrip("/")
    jira_email = os.getenv("JIRA_EMAIL", "")
    jira_token = os.getenv("JIRA_API_TOKEN", "")
    project_key = os.getenv("JIRA_PROJECT_KEY", "SCRUM")

    if not all([jira_url, jira_email, jira_token]):
        st.error("Jira credentials not configured.")
        return

    auth_token = b64encode(f"{jira_email}:{jira_token}".encode()).decode()
    headers = {
        "Authorization": f"Basic {auth_token}",
        "Content-Type": "application/json",
    }

    priority_map = {"critical": "Highest", "high": "High", "medium": "Medium", "low": "Low"}
    verification = st.session_state.get("verification_result")

    def _p(text):
        return {"type": "paragraph", "content": [{"type": "text", "text": text}]}

    def _h(text, level=2):
        return {"type": "heading", "attrs": {"level": level}, "content": [{"type": "text", "text": text}]}

    def _code(text):
        return {"type": "codeBlock", "attrs": {"language": "text"}, "content": [{"type": "text", "text": text}]}

    steps_text = "\n".join(f"{i+1}. {s}" for i, s in enumerate(bug.get("steps_to_reproduce", [])))

    content = [
        _h("Description"),
        _p(bug["description"]),
        _h("Steps to Reproduce"),
        _p(steps_text),
        _h("Expected Behaviour"),
        _p(bug["expected_behaviour"]),
        _h("Actual Behaviour"),
        _p(bug["actual_behaviour"]),
        _h("Affected Feature"),
        _p(bug["affected_feature"]),
    ]

    # Include verification result if available
    if verification:
        confirmed = "CONFIRMED" if verification.bug_confirmed else "NOT REPRODUCED"
        content += [
            _h("Verification Result"),
            _p(f"Status: {confirmed} ({verification.confidence} confidence)\n{verification.summary}"),
        ]
        if verification.reproduction_url:
            content.append(_p(f"Failed at URL: {verification.reproduction_url}"))
        if verification.failing_step:
            content.append(_p(f"Bug appeared at step: {verification.failing_step}"))

        # Step-by-step observations
        if verification.steps:
            content.append(_h("Step-by-Step Observations"))
            for step in verification.steps:
                status = "PASS" if step.success else "FAIL"
                content.append(_p(f"[{status}] Step {step.step_number}: {step.step_description}\n→ {step.observation}"))

        # Console errors
        if verification.console_errors:
            content.append(_h("Console Errors"))
            content.append(_code("\n".join(verification.console_errors)))

    payload = {
        "fields": {
            "project": {"key": project_key},
            "summary": bug["title"],
            "description": {"type": "doc", "version": 1, "content": content},
            "issuetype": {"name": "Bug"},
            "priority": {"name": priority_map.get(bug["priority"], "Medium")},
            "labels": [l.replace(" ", "-") for l in bug.get("labels", [])] + ["bug-agent"],
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

        attach_headers = {
            "Authorization": f"Basic {auth_token}",
            "X-Atlassian-Token": "no-check",
        }

        # User-uploaded attachments
        if attachments:
            for f in attachments:
                with st.spinner(f"Attaching {f.name}..."):
                    file_bytes = f.read()
                    attach_resp = httpx.post(
                        f"{jira_url}/rest/api/3/issue/{ticket_key}/attachments",
                        headers=attach_headers,
                        files={"file": (f.name, file_bytes, f.type)},
                        timeout=60,
                    )
                    attach_resp.raise_for_status()

        # Auto-captured verification screenshots
        auto_screenshots = st.session_state.get("auto_screenshots", [])
        if auto_screenshots:
            for sc in auto_screenshots:
                with st.spinner(f"Attaching {sc['name']}..."):
                    attach_resp = httpx.post(
                        f"{jira_url}/rest/api/3/issue/{ticket_key}/attachments",
                        headers=attach_headers,
                        files={"file": (sc["name"], sc["bytes"], sc["type"])},
                        timeout=60,
                    )
                    attach_resp.raise_for_status()

        st.success(f"Ticket created: [{ticket_key}]({ticket_url})")
        st.markdown(f"**[Open in Jira]({ticket_url})**")

        del st.session_state["generated_bug"]
        if "attachments" in st.session_state:
            del st.session_state["attachments"]

    except Exception as e:
        st.error(f"Failed to push to Jira: {e}")


# ── Page ──────────────────────────────────────────────────────────────────────
st.title("Report a Bug")
st.markdown("Describe the bug in plain English — the AI will structure it into a proper ticket.")

# ── Input Form ────────────────────────────────────────────────────────────────
with st.form("bug_form"):
    description = st.text_area(
        "Describe the bug",
        height=150,
        placeholder=(
            "e.g. When I try to log in on Safari mobile after entering the wrong "
            "password once, the login button becomes unresponsive and I have to "
            "refresh the page to try again."
        ),
    )

    col1, col2 = st.columns(2)
    with col1:
        project = st.text_input("Project / Product", value=os.getenv("PROJECT_NAME", "SportIQ"))
    with col2:
        reporter = st.text_input("Your name", placeholder="e.g. Jane Smith")

    attachments = st.file_uploader(
        "Attach screenshot, screen recording or zip bundle (optional)",
        type=["png", "jpg", "jpeg", "gif", "mp4", "mov", "webm", "zip"],
        accept_multiple_files=True,
    )

    submitted = st.form_submit_button("Generate Bug Report", type="primary")

# ── AI Analysis ───────────────────────────────────────────────────────────────
if submitted:
    if not description.strip():
        st.error("Please describe the bug first.")
        st.stop()

    with st.spinner("Analysing with AI..."):
        try:
            client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

            prompt = f"""You are a senior QA engineer. A team member has reported a bug in plain English.
Convert it into a structured, professional bug report.

Bug description from team member:
\"\"\"{description}\"\"\"

Project: {project}
Reporter: {reporter or "Team member"}

Respond ONLY with valid JSON in this exact schema:
{{
  "title": "short, clear bug title (max 100 chars)",
  "description": "clear description of the bug and its impact",
  "steps_to_reproduce": ["step 1", "step 2", "step 3"],
  "expected_behaviour": "what should happen",
  "actual_behaviour": "what actually happens",
  "priority": "critical|high|medium|low",
  "labels": ["label1", "label2"],
  "affected_feature": "the feature/module affected"
}}

Rules:
- steps_to_reproduce must be CONCRETE INTERACTION steps a browser automation tool can execute
- Every step must be an ACTION: navigate to URL, click a button, type text, select option
- NEVER use passive steps like "observe", "notice", "see", "check" — only actions
- Always include the step that TRIGGERS the bug (e.g. "Type 'messi vs ronaldo' in the search field and click ANALYSE")
- Last step should be the action that exposes the bug, not an observation
- priority: critical=data loss/app crash, high=major feature broken, medium=degraded UX, low=minor/cosmetic
- labels: use kebab-case, max 3 labels
- Keep everything concise and actionable"""

            message = client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=1024,
                messages=[{"role": "user", "content": prompt}],
            )

            raw = message.content[0].text.strip()
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            bug = json.loads(raw.strip())
            st.session_state["generated_bug"] = bug
            st.session_state["attachments"] = attachments
            st.session_state["reporter"] = reporter

        except Exception as e:
            st.error(f"AI analysis failed: {e}")
            st.stop()

# ── Review & Edit ─────────────────────────────────────────────────────────────
if "generated_bug" in st.session_state:
    bug = st.session_state["generated_bug"]

    st.divider()
    st.subheader("Review & Edit Bug Report")
    st.markdown("Edit any field before pushing to Jira.")

    col1, col2 = st.columns([3, 1])
    with col1:
        bug["title"] = st.text_input("Title", value=bug["title"])
    with col2:
        bug["priority"] = st.selectbox(
            "Priority",
            ["critical", "high", "medium", "low"],
            index=["critical", "high", "medium", "low"].index(bug.get("priority", "medium")),
        )

    bug["description"] = st.text_area("Description", value=bug["description"], height=100)

    st.markdown("**Steps to Reproduce**")
    steps = bug.get("steps_to_reproduce", [])
    new_steps = []
    for i, step in enumerate(steps):
        edited = st.text_input(f"Step {i+1}", value=step, key=f"step_{i}")
        new_steps.append(edited)

    if st.button("+ Add step"):
        new_steps.append("")
    bug["steps_to_reproduce"] = [s for s in new_steps if s.strip()]

    col3, col4 = st.columns(2)
    with col3:
        bug["expected_behaviour"] = st.text_area(
            "Expected Behaviour", value=bug["expected_behaviour"], height=80
        )
    with col4:
        bug["actual_behaviour"] = st.text_area(
            "Actual Behaviour", value=bug["actual_behaviour"], height=80
        )

    labels_str = st.text_input(
        "Labels (comma-separated)", value=", ".join(bug.get("labels", []))
    )
    bug["labels"] = [l.strip() for l in labels_str.split(",") if l.strip()]

    bug["affected_feature"] = st.text_input(
        "Affected Feature", value=bug.get("affected_feature", "")
    )

    attachments = st.session_state.get("attachments", [])
    if attachments:
        st.markdown(f"**Attachments ({len(attachments)})**")
        for f in attachments:
            if f.type.startswith("image"):
                st.image(f, caption=f.name, width=300)
            elif f.type.startswith("video"):
                st.video(f)
            elif f.name.endswith(".zip") or f.type == "application/zip":
                st.markdown(f"📦 `{f.name}` — zip bundle ({round(f.size/1024, 1)} KB)")
            else:
                st.markdown(f"- `{f.name}` ({f.type})")

    st.divider()
    col_verify, col_push = st.columns([1, 1])

    with col_verify:
        if st.button("Verify Bug on App", type="secondary"):
            _verify_bug_on_app(bug)

    with col_push:
        if st.button("Push to Jira", type="primary"):
            _push_manual_bug_to_jira(bug, attachments)

    # Show verification results if available
    if "verification_result" in st.session_state:
        _show_verification_result(st.session_state["verification_result"])
