"""
Lightweight local verification service.
Runs on the HOST machine (not in Docker) so Playwright can reach localhost:3000 directly.
Start with: python3 verify_service.py
"""
from __future__ import annotations

import base64
import json
import logging
import os
import subprocess
import tempfile
import time
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

load_dotenv(Path(__file__).parent / ".env")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


APP_URL = os.getenv("APP_URL_LOCAL", "http://localhost:3000")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

APP_UI_HINTS = """
Known UI elements in this app:
- Main search input: input[placeholder='Ask anything about football...']
- Submit/Analyse button: button:has-text('ANALYSE →')
- Dual Analyst nav: button:has-text('DUAL ANALYST')
- Player Profile nav: button:has-text('PLAYER PROFILE')
- Head to Head nav: button:has-text('HEAD TO HEAD')
- Sign In button: button:has-text('SIGN IN')
"""

log.info(f"APP_URL: {APP_URL}")
log.info(f"ANTHROPIC_API_KEY loaded: {'yes' if ANTHROPIC_API_KEY else 'NO - MISSING'}")


_VERCEL_STORAGE_STATE = None

def _bypass_headers() -> dict:
    return {}

def _add_bypass(url: str) -> str:
    return url


class VerifyRequest(BaseModel):
    steps: list[str]
    description: str


class ElementScreenshotRequest(BaseModel):
    url: str
    selector: str = ""


ACTION_PROMPT = """You are controlling a web browser to reproduce a bug.

Current page URL: {url}
Current page title: {title}

Step to execute: "{step}"

Return a JSON action:
{{
  "action": "navigate|click|type|press_enter|scroll|wait|assert",
  "selector": "CSS selector or text selector",
  "value": "text to type or URL",
  "description": "what you are doing"
}}

Selector tips:
- Use "button:has-text('ANALYSE')" for buttons with text
- Use "textarea" or "input[type='text']" for text inputs
- Use "text=Login" for elements containing text
- Use placeholder: "input[placeholder='Ask anything...']"

{ui_hints}

Important: Always use the known UI selectors above when available.
Respond ONLY with valid JSON."""

VISION_PROMPT = """You are verifying a bug reproduction step.

Step: "{step}"
Action: "{action}"

--- NETWORK LOGS (requests made during this step) ---
{network_logs}

--- CONSOLE OUTPUT ---
{console_logs}

Look at the screenshot and the logs above together:
1. Did the action succeed?
2. What is visible on screen?
3. Check network logs — did any API call fail (4xx/5xx)? What was the error response?
4. Are there errors, "Connection error", broken UI, or failed API responses visible?

The root cause is often in the network logs, not just the screenshot.
For example: a UI showing "Connection error" is caused by a failed API call in the logs.

Respond with JSON:
{{
  "success": true/false,
  "observation": "what you see on screen AND what the network/console logs reveal",
  "bug_signs": "describe the root cause from logs + UI, or null if everything looks normal",
  "failed_requests": ["list any failed API URLs with status codes"]
}}"""

VERDICT_PROMPT = """You are a QA engineer reviewing browser automation results.

Bug description: "{description}"

Step observations:
{steps_summary}

Console errors: {console_errors}

Based on the screenshots AND network logs, determine:
- Was the bug confirmed?
- What was the root cause? (prefer network/API evidence over UI observations)
- At which step did it fail?

Respond with JSON:
{{
  "bug_confirmed": true/false,
  "confidence": "high|medium|low",
  "summary": "2-3 sentences — include the actual API error or network failure if found",
  "failing_step": null or step number,
  "root_cause": "API endpoint + error, or UI issue if no network evidence"
}}"""


def _get_action(page, step: str) -> dict:
    import anthropic
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    try:
        log.info(f"Getting action for step: {step[:60]}")
        r = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=512,
            messages=[{"role": "user", "content": ACTION_PROMPT.format(
                url=page.url, title=page.title(), step=step, ui_hints=APP_UI_HINTS
            )}]
        )
        raw = r.content[0].text.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        action = json.loads(raw.strip())
        log.info(f"Action: {action}")
        return action
    except Exception as e:
        log.error(f"_get_action failed: {e}")
        return {"action": "wait", "description": step}




def _execute_action(page, action: dict) -> bool:
    log.info(f"Executing: {action.get('action')} selector={action.get('selector')} value={action.get('value','')[:40]}")
    try:
        act = action.get("action", "wait")
        selector = action.get("selector", "")
        value = action.get("value", "")

        if act == "navigate":
            url = value if value.startswith("http") else f"{APP_URL.rstrip('/')}/{value.lstrip('/')}"
            url = _add_bypass(url)
            if page.url.split("?")[0].rstrip("/") != url.split("?")[0].rstrip("/"):
                page.goto(url, wait_until="networkidle", timeout=30000)
        elif act == "click":
            page.locator(selector).first.click(timeout=5000)
        elif act == "type":
            el = page.locator(selector).first
            el.click(timeout=5000)
            el.fill(value, timeout=5000)
            time.sleep(0.3)
            for submit_sel in [
                "button:has-text('ANALYSE →')",
                "button:has-text('ANALYSE')",
                "button:has-text('SEARCH →')",
                "button:has-text('Analyse')",
                "button:has-text('Search')",
                "button[type='submit']",
            ]:
                try:
                    btn = page.locator(submit_sel).first
                    if btn.is_visible():
                        btn.click(timeout=2000)
                        break
                except Exception:
                    continue
            else:
                page.keyboard.press("Enter")
        elif act == "press_enter":
            page.locator(selector).first.press("Enter", timeout=5000)
        elif act == "scroll":
            page.mouse.wheel(0, 500)
        elif act == "assert":
            page.wait_for_selector(selector or f"text={value}", timeout=5000)
        elif act == "wait":
            time.sleep(1)

        time.sleep(0.8)
        return True
    except Exception:
        return False


def _format_network_logs(logs: list[dict]) -> str:
    if not logs:
        return "No network requests captured."
    lines = []
    for entry in logs:
        status = entry.get("status")
        method = entry.get("method", "")
        url = entry.get("url", "")
        # Skip static assets
        if any(url.endswith(ext) for ext in (".js", ".css", ".png", ".ico", ".woff", ".svg")):
            continue
        body = entry.get("response_body", "")
        line = f"[{status}] {method} {url}"
        if body:
            line += f"\n    Response: {body[:300]}"
        lines.append(line)
    return "\n".join(lines) if lines else "No API requests captured."


def _observe(page, step: str, action_desc: str, network_logs: list[dict], console_logs: list[str]) -> dict:
    import anthropic
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    try:
        png = base64.b64encode(page.screenshot()).decode()
        r = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=800,
            messages=[{"role": "user", "content": [
                {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": png}},
                {"type": "text", "text": VISION_PROMPT.format(
                    step=step,
                    action=action_desc,
                    network_logs=_format_network_logs(network_logs),
                    console_logs="\n".join(console_logs[-10:]) or "None",
                )}
            ]}]
        )
        raw = r.content[0].text.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        result = json.loads(raw.strip())
        result["screenshot_b64"] = png
        return result
    except Exception as e:
        try:
            fallback_png = base64.b64encode(page.screenshot()).decode()
        except Exception:
            fallback_png = ""
        return {"success": False, "observation": str(e), "bug_signs": None, "screenshot_b64": fallback_png, "failed_requests": []}


def _replay_with_trace(code: str) -> tuple[str, str]:
    """
    Extract page.* action lines from the codegen script and replay them
    in a fresh Playwright session with tracing. Runs in-process so it works
    inside a PyInstaller executable (no python3 subprocess needed).
    Returns (trace_b64, error_reason) — error_reason is "" on success.
    """
    if not code.strip():
        return "", "No recorded code found."

    page_actions = []
    for line in code.split("\n"):
        stripped = line.strip()
        if stripped.startswith("page.") and not stripped.startswith("page.wait_for_timeout"):
            page_actions.append(stripped)

    if not page_actions:
        log.warning("No page.* actions found in codegen output")
        return "", "Could not extract page actions from recorded script — unexpected codegen format."

    trace_path = tempfile.mktemp(suffix=".zip")

    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(viewport={"width": 1280, "height": 800})
            context.tracing.start(screenshots=True, snapshots=True, sources=True)
            page = context.new_page()
            try:
                page.set_default_timeout(10000)
                page.set_default_navigation_timeout(15000)
                for action_line in page_actions:
                    try:
                        exec(action_line, {"page": page})  # noqa: S102
                    except Exception as _e:
                        log.info(f"Step skipped: {_e}")
            except Exception as e:
                log.warning(f"Replay error: {e}")
            finally:
                try:
                    context.tracing.stop(path=trace_path)
                except Exception as e:
                    log.warning(f"tracing.stop failed: {e}")
                    return "", f"Trace could not be saved: {e}"
            try:
                context.close()
            except Exception:
                pass
            try:
                browser.close()
            except Exception:
                pass

        if Path(trace_path).exists():
            data = base64.b64encode(Path(trace_path).read_bytes()).decode()
            Path(trace_path).unlink(missing_ok=True)
            log.info(f"Trace captured — {len(data)} chars")
            return data, ""
        else:
            log.warning("Trace file not found after replay")
            return "", "Trace file was not written — browser may have crashed during replay."
    except Exception as e:
        log.warning(f"Trace replay exception: {e}")
        return "", f"Trace replay failed: {e}"


# ── Codegen recording state ───────────────────────────────────────────────────
_recording_process = None  # type: subprocess.Popen
_recording_output_file: str = ""


@app.post("/record/start")
def record_start():
    """Launch playwright codegen so the user can record reproduction steps."""
    global _recording_process, _recording_output_file

    if _recording_process and _recording_process.poll() is None:
        raise HTTPException(status_code=409, detail="Recording already in progress.")

    tmp = tempfile.NamedTemporaryFile(suffix=".py", delete=False)
    _recording_output_file = tmp.name
    tmp.close()

    log.info(f"Starting codegen → {_recording_output_file}")
    from playwright._impl._driver import compute_driver_executable
    node, cli = compute_driver_executable()
    _recording_process = subprocess.Popen(
        [str(node), str(cli), "codegen", "--target", "python", "--output", _recording_output_file, APP_URL],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return {"status": "recording", "message": "Browser opened — reproduce the bug then close the browser."}


@app.get("/record/status")
def record_status():
    """Poll this to know when the user has closed the browser."""
    global _recording_process
    if _recording_process is None:
        return {"status": "idle"}
    if _recording_process.poll() is None:
        return {"status": "recording"}
    return {"status": "done"}


@app.get("/record/finish")
def record_finish():
    """Read the recorded script and replay headlessly to capture trace.
    Step conversion to natural language is handled by the dashboard (no API key needed here).
    """
    global _recording_process, _recording_output_file

    if _recording_process is None:
        raise HTTPException(status_code=400, detail="No recording session found.")
    if _recording_process.poll() is None:
        raise HTTPException(status_code=400, detail="Recording still in progress — close the browser first.")

    code = Path(_recording_output_file).read_text() if _recording_output_file else ""
    Path(_recording_output_file).unlink(missing_ok=True)
    _recording_process = None

    if not code.strip():
        raise HTTPException(status_code=400, detail="No steps were recorded.")

    log.info(f"Recorded code ({len(code)} chars) — replaying for trace")
    trace_b64, trace_error = _replay_with_trace(code)
    return {"raw_code": code, "trace_b64": trace_b64, "trace_error": trace_error}


@app.post("/verify")
def verify(req: VerifyRequest):
    from playwright.sync_api import sync_playwright

    step_results = []
    console_errors = []
    console_all = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1280, "height": 800},
            storage_state=_VERCEL_STORAGE_STATE,
            extra_http_headers=_bypass_headers(),
        )
        context.tracing.start(screenshots=True, snapshots=True)
        page = context.new_page()

        # Capture console output
        page.on("console", lambda m: console_all.append(f"[{m.type}] {m.text}"))
        page.on("console", lambda m: console_errors.append(m.text) if m.type == "error" else None)
        page.on("pageerror", lambda e: console_errors.append(str(e)))

        # Network log buffer — cleared per step
        network_buffer: list[dict] = []

        def _on_response(response):
            try:
                # Only capture XHR/fetch (API calls), skip static assets
                resource_type = response.request.resource_type
                if resource_type not in ("xhr", "fetch", "websocket"):
                    return
                entry = {
                    "method": response.request.method,
                    "url": response.url,
                    "status": response.status,
                    "response_body": "",
                }
                # Capture body for failed or JSON responses
                if response.status >= 400 or "json" in (response.headers.get("content-type", "")):
                    try:
                        entry["response_body"] = response.text()[:500]
                    except Exception:
                        pass
                network_buffer.append(entry)
                if response.status >= 400:
                    log.warning(f"Failed request: [{response.status}] {response.request.method} {response.url}")
            except Exception:
                pass

        page.on("response", _on_response)

        try:
            page.goto(_add_bypass(APP_URL), wait_until="networkidle", timeout=30000)
        except Exception as e:
            browser.close()
            return {
                "bug_confirmed": False, "confidence": "low",
                "summary": f"Could not reach app at {APP_URL}: {e}",
                "steps": [], "console_errors": [], "reproduction_url": None, "failing_step": None
            }

        for i, step in enumerate(req.steps, 1):
            network_buffer.clear()
            step_console = list(console_all)  # snapshot before action

            action = _get_action(page, step)
            action_desc = action.get("description", step)
            success = _execute_action(page, action)
            time.sleep(1.0)  # let async responses complete

            step_network = list(network_buffer)
            step_console_new = console_all[len(step_console):]  # only logs from this step

            obs = _observe(page, step, action_desc, step_network, step_console_new)

            # Build human-readable network summary for this step
            failed = [e for e in step_network if e["status"] >= 400]
            network_summary = "; ".join(
                f"[{e['status']}] {e['method']} {e['url'].split('?')[0]}" for e in failed
            ) if failed else ""

            step_results.append({
                "step_number": i,
                "step_description": step,
                "action_taken": action_desc,
                "screenshot_b64": obs.get("screenshot_b64", ""),
                "success": success and obs.get("success", True),
                "observation": obs.get("observation", ""),
                "bug_signs": obs.get("bug_signs"),
                "failed_requests": obs.get("failed_requests", []) or ([network_summary] if network_summary else []),
            })

        reproduction_url = page.url

        trace_b64 = ""
        try:
            with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tf:
                trace_path = tf.name
            context.tracing.stop(path=trace_path)
            trace_b64 = base64.b64encode(Path(trace_path).read_bytes()).decode()
            Path(trace_path).unlink(missing_ok=True)
        except Exception as e:
            log.warning(f"Could not save trace: {e}")

        browser.close()

    steps_summary = "\n".join(
        f"Step {r['step_number']}: {r['step_description']}\n  → {r['observation']}"
        + (f"\n  ⚠ Bug signs: {r['bug_signs']}" if r.get("bug_signs") else "")
        + (f"\n  ✗ Failed requests: {'; '.join(r['failed_requests'])}" if r.get("failed_requests") else "")
        for r in step_results
    )

    import anthropic
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    try:
        vr = client.messages.create(
            model="claude-sonnet-4-6", max_tokens=600,
            messages=[{"role": "user", "content": VERDICT_PROMPT.format(
                description=req.description,
                steps_summary=steps_summary,
                console_errors=console_errors[:10],
            )}]
        )
        raw = vr.content[0].text.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        verdict = json.loads(raw.strip())
    except Exception:
        verdict = {"bug_confirmed": False, "confidence": "low", "summary": "Could not determine verdict.", "failing_step": None, "root_cause": None}

    return {
        "bug_confirmed": verdict.get("bug_confirmed", False),
        "confidence": verdict.get("confidence", "low"),
        "summary": verdict.get("summary", ""),
        "root_cause": verdict.get("root_cause", ""),
        "steps": step_results,
        "console_errors": console_errors[:10],
        "reproduction_url": reproduction_url,
        "failing_step": verdict.get("failing_step"),
        "trace_b64": trace_b64,
    }



@app.post("/element-screenshot")
def element_screenshot(req: ElementScreenshotRequest):
    """Navigate to a URL, highlight a CSS selector, and return a focused screenshot."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1280, "height": 800})
        page = context.new_page()

        try:
            page.goto(req.url, wait_until="networkidle", timeout=30000)
        except Exception as e:
            browser.close()
            raise HTTPException(status_code=400, detail=f"Could not load URL: {e}")

        element_found = False

        if req.selector:
            try:
                element = page.locator(req.selector).first
                element.wait_for(timeout=5000)

                # Highlight with a red outline so the issue is unmissable in Jira
                page.evaluate(f"""() => {{
                    const el = document.querySelector({json.dumps(req.selector)});
                    if (el) {{
                        el.style.outline = '3px solid #FF3B30';
                        el.style.outlineOffset = '3px';
                        el.style.boxShadow = '0 0 0 6px rgba(255,59,48,0.25)';
                    }}
                }}""")

                element.scroll_into_view_if_needed()
                page.wait_for_timeout(300)  # let highlight render

                box = element.bounding_box()
                if box:
                    padding = 48
                    clip = {
                        "x": max(0, box["x"] - padding),
                        "y": max(0, box["y"] - padding),
                        "width": min(1280, box["width"] + padding * 2),
                        "height": min(800, box["height"] + padding * 2),
                    }
                    png = page.screenshot(clip=clip)
                    element_found = True
                else:
                    png = page.screenshot()
            except Exception as e:
                log.warning(f"Selector '{req.selector}' not found: {e} — falling back to full page")
                png = page.screenshot()
        else:
            png = page.screenshot()

        screenshot_b64 = base64.b64encode(png).decode()
        browser.close()

    return {"screenshot_b64": screenshot_b64, "element_found": element_found}


@app.get("/health")
def health():
    return {"status": "ok", "app_url": APP_URL}


def _ensure_playwright_installed():
    """Install Playwright Chromium on first run (needed after exe download)."""
    try:
        from playwright._impl._driver import compute_driver_executable
        node, cli = compute_driver_executable()
        log.info("Checking Playwright Chromium installation...")
        result = subprocess.run(
            [str(node), str(cli), "install", "chromium"],
            capture_output=True, text=True, timeout=300,
        )
        if result.returncode == 0:
            log.info("Playwright Chromium ready.")
        else:
            log.warning(f"playwright install output: {result.stderr[:300]}")
    except Exception as e:
        log.warning(f"Could not auto-install Playwright Chromium: {e}")


if __name__ == "__main__":
    import uvicorn

    _ensure_playwright_installed()

    print("\n" + "=" * 52)
    print("  SportIQ Verify Agent — ready")
    print("=" * 52)
    print(f"  Running at: http://localhost:8502")
    print()
    print("  Paste this URL into the SportIQ Bug")
    print("  Dashboard to enable recording.")
    print("=" * 52 + "\n")

    uvicorn.run(app, host="0.0.0.0", port=8502)
