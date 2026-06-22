"""
Manual bug reporting page.
User writes in plain English → AI structures it → user reviews → push to Jira.
"""
import base64
import json
import os
import sys
import time
from base64 import b64encode

import anthropic
import httpx
import streamlit as st

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from utils import ICON, page_setup

st.set_page_config(page_title="Report a Bug", page_icon=ICON, layout="wide")
page_setup()

# ── Environment → Base URL mapping ────────────────────────────────────────────
_ENV_BASE_URLS = {
    "Production":  os.getenv("PROD_BASE_URL",    "https://api.sportiq.com"),
    "Staging":     os.getenv("STAGING_BASE_URL", "https://staging-api.sportiq.com"),
    "Development": os.getenv("DEV_BASE_URL",     "http://dev-api.sportiq.com"),
    "Local":       os.getenv("LOCAL_BASE_URL",   "http://localhost:3000"),
}


def _sync_base_url():
    env = st.session_state.get("api_env", "Production")
    st.session_state["api_base_url"] = _ENV_BASE_URLS.get(env, "")


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
        except Exception:
            st.warning("Local Agent not reachable — skipping verification. Bug will be pushed without screenshots.")
            return

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
            self.trace_b64 = d.get("trace_b64", "")

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

    if data.get("trace_b64"):
        auto_attachments.append({
            "name": "playwright_trace.zip",
            "bytes": base64.b64decode(data["trace_b64"]),
            "type": "application/zip",
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

    reporter_name = st.session_state.get("reporter_name", "").strip() or "Bug Tracking Agent"
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
        _h("Filed By"),
        _p(f"{reporter_name} · via Bug Tracking Agent"),
    ]

    api_details = st.session_state.get("api_details")
    if api_details:
        content.insert(0, _p(f"Environment: {api_details.get('env', 'Unknown')}"))
        content.insert(0, _h("Environment"))
        method_endpoint = f"{api_details.get('method', '')} {api_details.get('endpoint', '')}".strip()
        content.append(_h("API Evidence"))
        if api_details.get("base_url"):
            content.append(_p(f"Base URL: {api_details['base_url']}"))
        if method_endpoint:
            content.append(_p(f"Endpoint: {method_endpoint}"))
        if api_details.get("elapsed_ms"):
            content.append(_p(f"Response time: {api_details['elapsed_ms']}ms"))
        if api_details.get("request_headers"):
            content.append(_p("Request headers:"))
            content.append(_code("\n".join(f"{k}: {v}" for k, v in api_details["request_headers"].items())))
        if api_details.get("request"):
            content.append(_p("Request body:"))
            content.append(_code(api_details["request"]))
        if api_details.get("status"):
            content.append(_p(f"Response status: {api_details['status']}"))
        if api_details.get("response_headers"):
            content.append(_p("Response headers:"))
            content.append(_code("\n".join(f"{k}: {v}" for k, v in api_details["response_headers"].items())))
        if api_details.get("response"):
            content.append(_p("Response body:"))
            content.append(_code(api_details["response"][:3000]))

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
        if verification.steps:
            content.append(_h("Step-by-Step Observations"))
            for step in verification.steps:
                status = "PASS" if step.success else "FAIL"
                content.append(_p(f"[{status}] Step {step.step_number}: {step.step_description}\n→ {step.observation}"))
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

        def _attach(name, data_bytes, mime):
            try:
                r = httpx.post(
                    f"{jira_url}/rest/api/3/issue/{ticket_key}/attachments",
                    headers=attach_headers,
                    files={"file": (name, bytes(data_bytes), mime)},
                    timeout=60,
                )
                r.raise_for_status()
            except Exception as exc:
                st.warning(f"Could not attach {name}: {exc}")

        for f in (attachments or []):
            with st.spinner(f"Attaching {f.name}..."):
                _attach(f.name, f.read(), f.type)

        for sc in st.session_state.get("auto_screenshots", []):
            with st.spinner(f"Attaching {sc['name']}..."):
                _attach(sc["name"], sc["bytes"], sc["type"])

        st.success(f"Ticket created: [{ticket_key}]({ticket_url})")
        st.markdown(f"**[Open in Jira]({ticket_url})**")

        for key in ["generated_bug", "attachments", "verification_result",
                    "auto_screenshots", "api_details", "recorded_steps",
                    "api_response_data", "api_request_headers"]:
            st.session_state.pop(key, None)

    except Exception as e:
        st.error(f"Failed to push to Jira: {e}")


# ── Record Steps via Playwright Codegen ───────────────────────────────────────
def _record_steps():
    verify_url = os.getenv("VERIFY_SERVICE_URL", "http://host.docker.internal:8502")
    try:
        resp = httpx.post(f"{verify_url}/record/start", timeout=10)
        resp.raise_for_status()
        st.session_state["recording"] = True
        st.info("Browser opened on your machine — reproduce the bug, then close the browser.")
    except Exception as e:
        st.error(f"Could not start recording: {e}\n\nMake sure verify_service.py is running.")


def _finish_recording():
    verify_url = os.getenv("VERIFY_SERVICE_URL", "http://host.docker.internal:8502")
    try:
        status = httpx.get(f"{verify_url}/record/status", timeout=5).json()
        if status.get("status") == "recording":
            st.warning("Still recording — close the browser first.")
            return

        with st.spinner("Converting steps and replaying to capture screenshots + trace..."):
            resp = httpx.get(f"{verify_url}/record/finish", timeout=120)
            resp.raise_for_status()
            data = resp.json()

        steps = data.get("steps", [])
        if not steps:
            st.error(f"Could not convert steps: {data.get('error', 'Unknown error')}")
            return

        st.session_state["recorded_steps"] = steps
        st.session_state["recording"] = False

        if data.get("trace_b64"):
            st.session_state["auto_screenshots"] = [{
                "name": "playwright_trace.zip",
                "bytes": base64.b64decode(data["trace_b64"]),
                "type": "application/zip",
            }]
            st.success(f"Recorded {len(steps)} steps + Playwright trace captured — will attach to Jira automatically.")
        else:
            st.success(f"Recorded {len(steps)} steps — trace unavailable (verify service may be offline).")
    except Exception as e:
        st.error(f"Failed to finish recording: {e}")


# ── Page ──────────────────────────────────────────────────────────────────────
st.title("Report a Bug")
st.markdown("Choose the bug type — UI bugs are verified on the browser, API bugs are run live and captured with full request/response evidence.")

tab_ui, tab_api = st.tabs(["UI Bug", "API Bug"])

# ── UI Bug Tab ────────────────────────────────────────────────────────────────
with tab_ui:
    with st.expander("Record reproduction steps on your app (recommended)", expanded=False):
        st.markdown(
            "Opens a browser on your machine via Playwright. Reproduce the bug, "
            "close the browser, and the steps will be auto-populated in the form."
        )
        st.info(
            "A **Playwright trace** (screenshots at every action + full network log) "
            "will be captured automatically and attached to the Jira ticket — "
            "no extra steps needed. Open it at [trace.playwright.dev](https://trace.playwright.dev) to replay the bug.",
            icon="ℹ️",
        )
        rc1, rc2 = st.columns(2)
        with rc1:
            if st.button("Record Steps", type="secondary", use_container_width=True):
                _record_steps()
        with rc2:
            if st.button("Finish Recording", type="secondary", use_container_width=True):
                _finish_recording()

        if st.session_state.get("recorded_steps"):
            st.markdown("**Recorded steps** — edit or remove any step:")
            updated_steps = []
            for i, step in enumerate(st.session_state["recorded_steps"]):
                col_txt, col_del = st.columns([10, 1])
                with col_txt:
                    edited = st.text_input(f"Step {i+1}", value=step, key=f"rec_step_{i}", label_visibility="collapsed")
                with col_del:
                    remove = st.button("✕", key=f"rec_del_{i}", help="Remove this step")
                if not remove:
                    updated_steps.append(edited)
            st.session_state["recorded_steps"] = [s for s in updated_steps if s.strip()]

    st.markdown("**Describe the bug** <span style='color:red'>\\*</span>", unsafe_allow_html=True)
    ui_description = st.text_area(
        "Describe the bug",
        height=150,
        placeholder=(
            "e.g. When I try to log in on Safari mobile after entering the wrong "
            "password once, the login button becomes unresponsive and I have to "
            "refresh the page to try again."
        ),
        key="ui_description",
        label_visibility="collapsed",
    )
    ui_project = st.text_input("Project / Product", value=os.getenv("PROJECT_NAME", "SportIQ"), key="ui_project")

    st.file_uploader(
        "Attach files — drag & drop or click to browse (screenshots, recordings, zips)",
        type=["png", "jpg", "jpeg", "gif", "mp4", "mov", "webm", "zip"],
        accept_multiple_files=True,
        key="ui_attachments",
        help="Drag and drop any supporting evidence here. All files will be attached to the Jira ticket.",
    )
    st.caption("Tip: drag and drop multiple files at once for quicker upload.")

    st.markdown("---")
    st.markdown("**Your Name**")
    st.text_input(
        "your_name_ui",
        value=st.session_state.get("reporter_name", ""),
        placeholder="e.g. Jane Smith",
        label_visibility="collapsed",
        key="reporter_name",
    )
    ui_submitted = st.button("Draft Bug Ticket", type="primary", key="ui_submit")

# ── API Bug Tab ────────────────────────────────────────────────────────────────
with tab_api:
    st.markdown("Build your request, run it live, and capture the full response as a bug ticket.")

    # Initialise base URL in session state
    if "api_base_url" not in st.session_state:
        st.session_state["api_base_url"] = _ENV_BASE_URLS["Production"]

    # Environment + Base URL
    env_col, base_url_col = st.columns([1, 3])
    with env_col:
        api_env = st.selectbox(
            "Environment",
            list(_ENV_BASE_URLS.keys()),
            key="api_env",
            on_change=_sync_base_url,
        )
    with base_url_col:
        api_base_url = st.text_input("Base URL", key="api_base_url")

    # Method + Endpoint
    method_col, endpoint_col = st.columns([1, 4])
    with method_col:
        api_method = st.selectbox("Method", ["GET", "POST", "PUT", "PATCH", "DELETE"], key="api_method")
    with endpoint_col:
        api_endpoint = st.text_input("Endpoint", placeholder="/api/v1/compare", key="api_endpoint")

    # Headers editor
    st.markdown("**Headers**")
    if "api_headers" not in st.session_state:
        st.session_state["api_headers"] = [{"key": "Content-Type", "value": "application/json"}]

    updated_headers = []
    for i, h in enumerate(st.session_state["api_headers"]):
        hk_col, hv_col, hdel_col = st.columns([3, 5, 1])
        with hk_col:
            k = st.text_input("Key", value=h["key"], key=f"hk_{i}",
                               label_visibility="collapsed", placeholder="Header name")
        with hv_col:
            v = st.text_input("Value", value=h["value"], key=f"hv_{i}",
                               label_visibility="collapsed", placeholder="Value")
        with hdel_col:
            remove = st.button("✕", key=f"hdel_{i}")
        if not remove:
            updated_headers.append({"key": k, "value": v})
    st.session_state["api_headers"] = updated_headers

    if st.button("+ Add Header", key="add_header"):
        st.session_state["api_headers"].append({"key": "", "value": ""})
        st.rerun()

    # Request Body
    api_request = st.text_area(
        "Request Body (JSON)",
        height=100,
        placeholder='{"player1": "Messi", "player2": "Ronaldo", "sport": "football"}',
        key="api_request",
    )

    # Run Request
    if st.button("▶  Run Request", type="secondary", key="run_request"):
        ep = st.session_state.get("api_endpoint", "").strip()
        base = st.session_state.get("api_base_url", "").rstrip("/")
        full_url = f"{base}/{ep.lstrip('/')}" if ep else base

        req_headers_dict = {
            h["key"]: h["value"]
            for h in st.session_state["api_headers"]
            if h["key"].strip()
        }
        req_kwargs: dict = {"headers": req_headers_dict, "timeout": 30}
        body_text = st.session_state.get("api_request", "").strip()
        if body_text and st.session_state.get("api_method", "GET") not in ("GET",):
            try:
                req_kwargs["json"] = json.loads(body_text)
            except json.JSONDecodeError:
                req_kwargs["content"] = body_text.encode()

        with st.spinner(f"Running {st.session_state.get('api_method', 'GET')} {full_url}..."):
            try:
                t0 = time.time()
                r = httpx.request(st.session_state.get("api_method", "GET"), full_url, **req_kwargs)
                elapsed_ms = int((time.time() - t0) * 1000)
                st.session_state["api_response_data"] = {
                    "status": r.status_code,
                    "elapsed_ms": elapsed_ms,
                    "body": r.text,
                    "headers": dict(r.headers),
                }
                st.session_state["api_request_headers"] = req_headers_dict
                st.rerun()
            except Exception as exc:
                st.error(f"Request failed: {exc}")

    # Response panel
    resp_data = st.session_state.get("api_response_data")
    if resp_data:
        st.divider()
        ok = resp_data["status"] < 400
        color = "#28a745" if ok else "#dc3545"
        badge = "✅" if ok else "❌"
        st.markdown(
            f"<span style='font-weight:700; font-size:15px; color:{color}'>"
            f"{badge} {resp_data['status']}</span>"
            f"&emsp;<span style='color:#888; font-size:13px'>{resp_data['elapsed_ms']} ms</span>",
            unsafe_allow_html=True,
        )
        rb_tab, rh_tab = st.tabs(["Response Body", "Response Headers"])
        with rb_tab:
            try:
                st.code(json.dumps(json.loads(resp_data["body"]), indent=2), language="json")
            except Exception:
                st.code(resp_data["body"], language="text")
        with rh_tab:
            for k, v in resp_data["headers"].items():
                st.text(f"{k}: {v}")

    st.divider()
    st.markdown("**What's wrong with this response?**")
    api_description = st.text_area(
        "api_desc_input",
        height=80,
        placeholder="e.g. Returns 200 but the player stats are fabricated — player has no data in the DB",
        key="api_description",
        label_visibility="collapsed",
    )
    api_project = st.text_input("Project / Product", value=os.getenv("PROJECT_NAME", "SportIQ"), key="api_project")

    st.markdown("---")
    st.markdown("**Your Name**")
    st.text_input(
        "your_name_api",
        value=st.session_state.get("reporter_name", ""),
        placeholder="e.g. Jane Smith",
        label_visibility="collapsed",
        key="reporter_name_api",
    )
    api_submitted = st.button("Draft Bug Ticket", type="primary", key="api_submit")

# ── UI Bug AI Analysis ────────────────────────────────────────────────────────
if ui_submitted:
    ui_desc = st.session_state.get("ui_description", "")
    if not ui_desc.strip():
        st.error("Please describe the bug first.")
        st.stop()

    with st.spinner("Analysing with AI..."):
        try:
            client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
            recorded_steps = st.session_state.get("recorded_steps", [])
            steps_context = ""
            if recorded_steps:
                steps_context = "\n\nRecorded reproduction steps (use these exactly as steps_to_reproduce):\n" + \
                    "\n".join(f"{i+1}. {s}" for i, s in enumerate(recorded_steps))

            prompt = f"""You are a senior QA engineer. Convert this UI bug report into a structured ticket.

Bug description: \"\"\"{ui_desc}\"\"\"
Project: {st.session_state.get("ui_project", "")}
Reporter: {st.session_state.get("reporter_name", "") or "Team member"}
{steps_context}

Respond ONLY with valid JSON:
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
- If recorded steps provided, use them exactly — do not invent steps
- Every step must be a concrete ACTION (navigate, click, type, select)
- NEVER use passive steps like "observe", "notice", "see", "check"
- Include the step that TRIGGERS the bug
- priority: critical=data loss/crash, high=major feature broken, medium=degraded UX, low=cosmetic
- labels: kebab-case, max 3"""

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
            bug["_type"] = "ui"
            st.session_state["generated_bug"] = bug
            st.session_state["attachments"] = st.session_state.get("ui_attachments") or []
        except Exception as e:
            st.error(f"AI analysis failed: {e}")
            st.stop()

# ── API Bug AI Analysis ───────────────────────────────────────────────────────
if api_submitted:
    if st.session_state.get("reporter_name_api"):
        st.session_state["reporter_name"] = st.session_state["reporter_name_api"]

    api_ep = st.session_state.get("api_endpoint", "").strip()
    api_en = st.session_state.get("api_env", "Production")
    api_base = st.session_state.get("api_base_url", "").rstrip("/")
    resp_data = st.session_state.get("api_response_data")

    if not api_ep:
        st.error("Endpoint is required.")
        st.stop()
    if not resp_data:
        st.error("Please run the request first to capture the response.")
        st.stop()

    meth = st.session_state.get("api_method", "POST")
    req_body = st.session_state.get("api_request", "")
    req_headers = st.session_state.get("api_request_headers", {})
    resp_body = resp_data["body"]
    resp_headers = resp_data["headers"]
    elapsed_ms = resp_data.get("elapsed_ms")
    api_st = str(resp_data["status"])
    extra = st.session_state.get("api_description", "")

    req_headers_text = "\n".join(f"{k}: {v}" for k, v in req_headers.items()) if req_headers else "N/A"
    resp_headers_text = "\n".join(f"{k}: {v}" for k, v in list(resp_headers.items())[:15]) if resp_headers else "N/A"

    with st.spinner("Analysing with AI..."):
        try:
            client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

            prompt = f"""You are a senior QA engineer creating a bug ticket for an API failure.

Environment: {api_en}
Full URL: {api_base}/{api_ep.lstrip("/")}
Method: {meth}
Request headers:
{req_headers_text}
Request body: {req_body or "N/A"}
Response status: {api_st}
Response time: {elapsed_ms}ms
Response headers:
{resp_headers_text}
Response body: {resp_body[:2000] if resp_body else "N/A"}
What's wrong: {extra or "Not specified"}

Project: {st.session_state.get("api_project", "")}
Reporter: {st.session_state.get("reporter_name", "") or "Team member"}

Respond ONLY with valid JSON:
{{
  "title": "METHOD /endpoint returns STATUS — max 100 chars",
  "description": "Precise description including environment, what was called, and what went wrong",
  "steps_to_reproduce": ["curl command with exact headers and body to reproduce"],
  "expected_behaviour": "Expected HTTP status and response format",
  "actual_behaviour": "Actual HTTP status and exact error returned",
  "priority": "critical|high|medium|low",
  "labels": ["api", "environment-kebab-case", "optional-third"],
  "affected_feature": "API endpoint or service name"
}}

Rules:
- Title MUST follow: "METHOD /path returns STATUS"
- steps_to_reproduce must be curl commands with exact headers and body
- labels must include "api" and environment in kebab-case
- If Production, default priority to high or critical
- actual_behaviour must quote exact error from response body
- priority: critical=production down/data loss, high=production degraded, medium=non-prod, low=cosmetic"""

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
            bug["_type"] = "api"
            bug["_env"] = api_en
            st.session_state["generated_bug"] = bug
            st.session_state["attachments"] = []
            st.session_state["api_details"] = {
                "env": api_en,
                "method": meth,
                "endpoint": api_ep,
                "base_url": api_base,
                "request": req_body,
                "request_headers": req_headers,
                "status": api_st,
                "response": resp_body,
                "response_headers": dict(list(resp_headers.items())[:15]),
                "elapsed_ms": elapsed_ms,
            }
        except Exception as e:
            st.error(f"AI analysis failed: {e}")
            st.stop()

# ── Review & Edit ─────────────────────────────────────────────────────────────
if "generated_bug" in st.session_state:
    bug = st.session_state["generated_bug"]
    bug_type = bug.get("_type", "ui")

    st.divider()
    st.subheader("Review & Edit Bug Report")

    col1, col2 = st.columns([3, 1])
    with col1:
        bug["title"] = st.text_input("Title", value=bug["title"])
    with col2:
        bug["priority"] = st.selectbox(
            "Priority",
            ["critical", "high", "medium", "low"],
            index=["critical", "high", "medium", "low"].index(bug.get("priority", "medium")),
        )

    if bug_type == "api":
        api_details = st.session_state.get("api_details", {})
        env_options = ["Production", "Staging", "Development", "Local"]
        current_env = api_details.get("env", "Production")
        env_idx = env_options.index(current_env) if current_env in env_options else 0
        new_env = st.selectbox("Environment *", env_options, index=env_idx, key="review_env")
        api_details["env"] = new_env
        bug["_env"] = new_env
        st.session_state["api_details"] = api_details

    bug["description"] = st.text_area("Description", value=bug["description"], height=100)

    st.markdown("**Steps to Reproduce**")
    steps = bug.get("steps_to_reproduce", [])
    new_steps = []
    for i, step in enumerate(steps):
        col_s, col_d = st.columns([11, 1])
        with col_s:
            edited = st.text_input(f"Step {i+1}", value=step, key=f"step_{i}", label_visibility="collapsed")
        with col_d:
            remove = st.button("✕", key=f"del_step_{i}", help="Remove step")
        if not remove:
            new_steps.append(edited)
    if st.button("+ Add step"):
        new_steps.append("")
    bug["steps_to_reproduce"] = [s for s in new_steps if s.strip()]

    col3, col4 = st.columns(2)
    with col3:
        bug["expected_behaviour"] = st.text_area("Expected Behaviour", value=bug["expected_behaviour"], height=80)
    with col4:
        bug["actual_behaviour"] = st.text_area("Actual Behaviour", value=bug["actual_behaviour"], height=80)

    labels_str = st.text_input("Labels (comma-separated)", value=", ".join(bug.get("labels", [])))
    bug["labels"] = [l.strip() for l in labels_str.split(",") if l.strip()]
    bug["affected_feature"] = st.text_input("Affected Feature", value=bug.get("affected_feature", ""))

    attachments = st.session_state.get("attachments", [])
    if attachments:
        st.markdown(f"**Attachments ({len(attachments)})**")
        for f in attachments:
            if f.type.startswith("image"):
                st.image(f, caption=f.name, width=300)
            elif f.type.startswith("video"):
                st.video(f)
            else:
                st.markdown(f"- `{f.name}` ({f.type})")

    st.divider()
    if st.button("Push to Jira", type="primary"):
        _push_manual_bug_to_jira(bug, attachments)

    if "verification_result" in st.session_state:
        _show_verification_result(st.session_state["verification_result"])
