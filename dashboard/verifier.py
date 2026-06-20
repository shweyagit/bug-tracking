"""
Playwright-based bug verifier.
Takes steps to reproduce, executes them on the real app,
screenshots each step, and uses Claude vision to confirm the bug.
"""
import base64
import json
import os
import time
from dataclasses import dataclass, field
from typing import Optional

import anthropic
from playwright.sync_api import Page, sync_playwright

APP_URL = os.getenv("APP_URL", "http://host.docker.internal:3000")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)


@dataclass
class StepResult:
    step_number: int
    step_description: str
    action_taken: str
    screenshot_b64: str        # base64 encoded PNG
    success: bool
    observation: str           # Claude's observation of the screenshot


@dataclass
class VerificationResult:
    bug_confirmed: bool
    confidence: str            # high | medium | low
    summary: str
    steps: list[StepResult] = field(default_factory=list)
    console_errors: list[str] = field(default_factory=list)
    failing_step: Optional[int] = None
    reproduction_url: Optional[str] = None


ACTION_PROMPT = """You are controlling a web browser to reproduce a bug.

Current page URL: {url}
Current page title: {title}

Step to execute: "{step}"

Based on the step description, return a JSON action to perform:
{{
  "action": "navigate|click|type|select|scroll|wait|hover|assert",
  "selector": "CSS selector or text (for click/type/hover/assert)",
  "value": "text to type or URL to navigate to (if applicable)",
  "description": "what you are doing"
}}

Action types:
- navigate: go to a URL (set value to the URL, relative paths ok e.g. /login)
- click: click an element (use selector)
- type: type text into focused or selected input (use selector + value)
- press_enter: press Enter on an element (use selector)
- select: select option from dropdown (use selector + value)
- scroll: scroll down the page
- wait: wait 1 second
- hover: hover over element (use selector)
- assert: verify something is visible (use selector or descriptive text in value)

For selectors prefer: button text, link text, placeholder text, label text.
Examples: "button:has-text('Submit')", "input[placeholder='Email']", "text=Login"

Important:
- If a step involves typing into a search field, ALWAYS follow it with a separate click action on the search/submit button
- If a step says "search for X" treat it as TWO actions: type into field, then click submit button
- Be explicit — never assume a field submits automatically

Respond ONLY with valid JSON."""

VISION_PROMPT = """You are verifying whether a bug reproduction step worked correctly.

Step being executed: "{step}"
Action taken: "{action}"

Look at this screenshot carefully and answer:
1. Did the action succeed?
2. What do you see on the screen?
3. Are there ANY error messages, "Connection error", loading failures, or broken UI visible — even if caused by a previous step or already present on page load?

Important: If you see "Connection error", error banners, failed API responses, broken components, or any unexpected state — report them even if the current step didn't directly cause them.

Respond with JSON:
{{
  "success": true/false,
  "observation": "1-2 sentence description of what you see including any errors",
  "bug_signs": "describe any errors or unexpected behaviour visible on screen, or null if everything looks normal"
}}"""

FINAL_VERDICT_PROMPT = """You are a QA engineer reviewing browser automation results.

Bug description: "{bug_description}"

Steps attempted and observations:
{steps_summary}

Console errors captured: {console_errors}

Based on the screenshots and observations, determine:
1. Was the bug confirmed? Consider:
   - Did any screenshot show "Connection error", error messages, broken UI, or failed API responses?
   - Even if a step action failed, could the bug still be visible in the screenshot?
   - If error signs appear in ANY step screenshot, the bug is confirmed.
2. At which step did the bug manifest?
3. Confidence level

Respond with JSON:
{{
  "bug_confirmed": true/false,
  "confidence": "high|medium|low",
  "summary": "2-3 sentence summary of what was observed including any errors seen on screen",
  "failing_step": null or step number where bug/error appeared
}}"""


def _screenshot_b64(page: Page) -> str:
    png_bytes = page.screenshot(full_page=False)
    return base64.b64encode(png_bytes).decode()


def _get_action(page: Page, step: str) -> dict:
    try:
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=512,
            messages=[{
                "role": "user",
                "content": ACTION_PROMPT.format(
                    url=page.url,
                    title=page.title(),
                    step=step,
                )
            }]
        )
        raw = response.content[0].text.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        return json.loads(raw.strip())
    except Exception:
        return {"action": "wait", "description": f"Could not parse step: {step}"}


def _execute_action(page: Page, action: dict) -> bool:
    try:
        act = action.get("action", "wait")
        selector = action.get("selector", "")
        value = action.get("value", "")

        if act == "navigate":
            if value.startswith("http"):
                url = value
            else:
                url = f"{APP_URL.rstrip('/')}/{value.lstrip('/')}"
            # Skip if already on this page
            if page.url.rstrip("/") != url.rstrip("/"):
                page.goto(url, wait_until="domcontentloaded", timeout=10000)
        elif act == "click":
            page.locator(selector).first.click(timeout=5000)
        elif act == "type":
            el = page.locator(selector).first
            el.click(timeout=5000)
            el.fill(value, timeout=5000)
            time.sleep(0.3)
            # Look for a submit button, fall back to Enter
            for submit_sel in [
                "button:has-text('Analyse')", "button:has-text('ANALYSE')",
                "button:has-text('Search')", "button:has-text('Submit')",
                "button[type='submit']", "button:has-text('→')",
            ]:
                try:
                    page.locator(submit_sel).first.click(timeout=2000)
                    break
                except Exception:
                    continue
            else:
                page.keyboard.press("Enter")
        elif act == "select":
            page.locator(selector).first.select_option(value, timeout=5000)
        elif act == "press_enter":
            page.locator(selector).first.press("Enter", timeout=5000)
        elif act == "hover":
            page.locator(selector).first.hover(timeout=5000)
        elif act == "scroll":
            page.mouse.wheel(0, 500)
        elif act == "assert":
            page.wait_for_selector(selector or f"text={value}", timeout=5000)
        elif act == "wait":
            time.sleep(1)

        time.sleep(0.8)  # brief pause for page to settle
        return True
    except Exception:
        return False


def _observe_screenshot(screenshot_b64: str, step: str, action_desc: str) -> dict:
    try:
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=512,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/png",
                            "data": screenshot_b64,
                        }
                    },
                    {
                        "type": "text",
                        "text": VISION_PROMPT.format(step=step, action=action_desc)
                    }
                ]
            }]
        )
        raw = response.content[0].text.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        return json.loads(raw.strip())
    except Exception:
        return {"success": False, "observation": "Could not analyse screenshot", "bug_signs": None}


def verify_bug(
    steps_to_reproduce: list[str],
    bug_description: str,
) -> VerificationResult:
    """
    Main entry point. Runs Playwright, follows steps, returns VerificationResult.
    """
    step_results: list[StepResult] = []
    console_errors: list[str] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--disable-setuid-sandbox",
                # Redirect localhost → host.docker.internal so app API calls work inside Docker
                "--host-resolver-rules=MAP localhost host.docker.internal",
            ],
        )
        context = browser.new_context(
            viewport={"width": 1280, "height": 800},
            # Bypass localtunnel / ngrok confirmation pages
            extra_http_headers={
                "bypass-tunnel-reminder": "true",
                "ngrok-skip-browser-warning": "true",
                "User-Agent": "Mozilla/5.0 (compatible; BugAgent/1.0)",
            },
        )
        page = context.new_page()

        # Capture console errors
        page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
        page.on("pageerror", lambda err: console_errors.append(str(err)))

        # Always start at the app root
        try:
            resp = page.goto(APP_URL, wait_until="domcontentloaded", timeout=15000)
            if resp and resp.status >= 500:
                browser.close()
                return VerificationResult(
                    bug_confirmed=False,
                    confidence="low",
                    summary=(
                        f"App returned {resp.status} at {APP_URL}. "
                        "The tunnel may be down — restart localtunnel/ngrok and update APP_URL."
                    ),
                )
        except Exception as e:
            browser.close()
            return VerificationResult(
                bug_confirmed=False,
                confidence="low",
                summary=(
                    f"Could not reach the app at {APP_URL}. "
                    "Check that your tunnel is running and APP_URL is current."
                ),
            )

        # Execute each step
        for i, step in enumerate(steps_to_reproduce, 1):
            action = _get_action(page, step)
            action_desc = action.get("description", step)

            success = _execute_action(page, action)
            screenshot_b64 = _screenshot_b64(page)
            observation = _observe_screenshot(screenshot_b64, step, action_desc)

            step_results.append(StepResult(
                step_number=i,
                step_description=step,
                action_taken=action_desc,
                screenshot_b64=screenshot_b64,
                success=success and observation.get("success", True),
                observation=observation.get("observation", ""),
            ))

        reproduction_url = page.url
        browser.close()

    # Final verdict from Claude
    steps_summary = "\n".join(
        f"Step {r.step_number}: {r.step_description}\n  → {r.observation}"
        for r in step_results
    )

    try:
        verdict_response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=512,
            messages=[{
                "role": "user",
                "content": FINAL_VERDICT_PROMPT.format(
                    bug_description=bug_description,
                    steps_summary=steps_summary,
                    console_errors=console_errors[:10],
                )
            }]
        )
        raw = verdict_response.content[0].text.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        verdict = json.loads(raw.strip())
    except Exception:
        verdict = {
            "bug_confirmed": False,
            "confidence": "low",
            "summary": "Could not determine verdict.",
            "failing_step": None,
        }

    return VerificationResult(
        bug_confirmed=verdict.get("bug_confirmed", False),
        confidence=verdict.get("confidence", "low"),
        summary=verdict.get("summary", ""),
        steps=step_results,
        console_errors=console_errors[:10],
        failing_step=verdict.get("failing_step"),
        reproduction_url=reproduction_url,
    )
