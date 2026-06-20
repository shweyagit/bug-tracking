"""
Lightweight local verification service.
Runs on the HOST machine (not in Docker) so Playwright can reach localhost:3000 directly.
Start with: python3 verify_service.py
"""
import base64
import json
import logging
import os
import time
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Load .env from project root
load_dotenv(Path(__file__).parent / ".env")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

APP_URL = os.getenv("APP_URL_LOCAL", "http://localhost:3000")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

# Known UI selectors for this app (discovered via Playwright inspection)
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


class VerifyRequest(BaseModel):
    steps: list[str]
    description: str


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

Look at the screenshot carefully:
1. Did the action succeed?
2. What is visible on screen?
3. Are there errors, "Connection error", broken UI, failed responses visible anywhere?

Respond with JSON:
{{
  "success": true/false,
  "observation": "what you see including any errors",
  "bug_signs": "any errors or broken behaviour visible, or null"
}}"""

VERDICT_PROMPT = """You are a QA engineer reviewing browser automation.

Bug description: "{description}"

Step observations:
{steps_summary}

Console errors: {console_errors}

Did any screenshot show errors, "Connection error", broken components or unexpected behaviour?
If yes, the bug is confirmed regardless of whether the step action succeeded.

Respond with JSON:
{{
  "bug_confirmed": true/false,
  "confidence": "high|medium|low",
  "summary": "2-3 sentences on what was observed",
  "failing_step": null or step number
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
            if page.url.rstrip("/") != url.rstrip("/"):
                page.goto(url, wait_until="domcontentloaded", timeout=15000)
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


def _observe(page, step: str, action_desc: str) -> dict:
    import anthropic
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    try:
        png = base64.b64encode(page.screenshot()).decode()
        r = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=512,
            messages=[{"role": "user", "content": [
                {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": png}},
                {"type": "text", "text": VISION_PROMPT.format(step=step, action=action_desc)}
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
        return {"success": False, "observation": str(e), "bug_signs": None, "screenshot_b64": fallback_png}


@app.post("/verify")
def verify(req: VerifyRequest):
    from playwright.sync_api import sync_playwright

    step_results = []
    console_errors = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1280, "height": 800})
        page = context.new_page()
        page.on("console", lambda m: console_errors.append(m.text) if m.type == "error" else None)
        page.on("pageerror", lambda e: console_errors.append(str(e)))

        try:
            page.goto(APP_URL, wait_until="domcontentloaded", timeout=15000)
        except Exception as e:
            browser.close()
            return {
                "bug_confirmed": False, "confidence": "low",
                "summary": f"Could not reach app at {APP_URL}: {e}",
                "steps": [], "console_errors": [], "reproduction_url": None, "failing_step": None
            }

        for i, step in enumerate(req.steps, 1):
            action = _get_action(page, step)
            action_desc = action.get("description", step)
            success = _execute_action(page, action)
            time.sleep(0.5)  # let page settle before screenshot
            obs = _observe(page, step, action_desc)

            step_results.append({
                "step_number": i,
                "step_description": step,
                "action_taken": action_desc,
                "screenshot_b64": obs.get("screenshot_b64", ""),
                "success": success and obs.get("success", True),
                "observation": obs.get("observation", ""),
                "bug_signs": obs.get("bug_signs"),
            })

        reproduction_url = page.url
        browser.close()

    steps_summary = "\n".join(
        f"Step {r['step_number']}: {r['step_description']}\n  → {r['observation']}"
        + (f"\n  ⚠ {r['bug_signs']}" if r.get("bug_signs") else "")
        for r in step_results
    )

    import anthropic
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    try:
        vr = client.messages.create(
            model="claude-sonnet-4-6", max_tokens=512,
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
        verdict = {"bug_confirmed": False, "confidence": "low", "summary": "Could not determine verdict.", "failing_step": None}

    return {
        "bug_confirmed": verdict.get("bug_confirmed", False),
        "confidence": verdict.get("confidence", "low"),
        "summary": verdict.get("summary", ""),
        "steps": step_results,
        "console_errors": console_errors[:10],
        "reproduction_url": reproduction_url,
        "failing_step": verdict.get("failing_step"),
    }


@app.get("/health")
def health():
    return {"status": "ok", "app_url": APP_URL}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8502)
