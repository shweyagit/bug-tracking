"""
Records a full demo of the Bug Tracking Agent workflow.
Saves MP4 video + screenshots to demo/ folder.

Run with:
    python3 record_demo.py

Prerequisites:
    - docker-compose up -d (all services running)
    - python3 verify_service.py (running in another terminal)
    - SportIQ app running on localhost:3000
    - Dashboard running on localhost:8501
"""
import os
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

DASHBOARD_URL = "http://localhost:8501"
DEMO_DIR = Path("demo")
DEMO_DIR.mkdir(exist_ok=True)
SCREENSHOTS_DIR = DEMO_DIR / "screenshots"
SCREENSHOTS_DIR.mkdir(exist_ok=True)

BUG_DESCRIPTION = (
    "In the Dual Analysis feature, when I type any search query and click ANALYSE, "
    "both the Tactical Analyst and Data & Stats panels show a Connection error instead "
    "of returning results. This completely breaks the Dual Analysis workflow."
)


def screenshot(page, name: str):
    path = str(SCREENSHOTS_DIR / f"{name}.png")
    page.screenshot(path=path, full_page=False)
    print(f"  📸 Screenshot: {name}.png")
    return path


def slow_type(page, selector: str, text: str, delay: int = 40):
    el = page.locator(selector).first
    el.click()
    for char in text:
        page.keyboard.type(char)
        time.sleep(delay / 1000)


def run_demo():
    print("\n🎬 Starting Bug Tracking Agent Demo Recording...\n")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)  # visible browser for recording
        context = browser.new_context(
            viewport={"width": 1400, "height": 900},
            record_video_dir=str(DEMO_DIR),
            record_video_size={"width": 1400, "height": 900},
        )
        page = context.new_page()

        # ── Step 1: Open Dashboard ─────────────────────────────────────────────
        print("Step 1: Opening Bug Tracking Agent dashboard...")
        page.goto(DASHBOARD_URL, wait_until="networkidle", timeout=30000)
        page.wait_for_timeout(3000)
        screenshot(page, "01_dashboard_home")

        # ── Step 2: Navigate to Report a Bug ──────────────────────────────────
        print("Step 2: Navigating to Report a Bug page...")
        # Click sidebar nav item
        page.locator("text=Report a Bug").first.click()
        page.wait_for_timeout(2000)
        screenshot(page, "02_report_bug_page")

        # ── Step 3: Type bug description ──────────────────────────────────────
        print("Step 3: Typing bug description...")
        textarea = page.locator("textarea").first
        textarea.click()
        page.wait_for_timeout(500)
        slow_type(page, "textarea", BUG_DESCRIPTION, delay=25)
        page.wait_for_timeout(1000)
        screenshot(page, "03_bug_description_typed")

        # ── Step 4: Generate Bug Report ───────────────────────────────────────
        print("Step 4: Clicking Generate Bug Report...")
        page.locator("button:has-text('Generate Bug Report')").first.click()
        page.wait_for_timeout(8000)  # wait for AI analysis
        screenshot(page, "04_bug_report_generated")

        # ── Step 5: Show generated fields ─────────────────────────────────────
        print("Step 5: Reviewing AI-generated bug report...")
        page.wait_for_timeout(2000)
        screenshot(page, "05_bug_report_review")

        # ── Step 6: Click Verify Bug on App ───────────────────────────────────
        print("Step 6: Clicking Verify Bug on App...")
        page.locator("button:has-text('Verify Bug on App')").first.click()
        print("  ⏳ Waiting for Playwright verification (this takes ~30 seconds)...")
        page.wait_for_timeout(45000)
        screenshot(page, "06_verification_result")

        # ── Step 7: Scroll through verification result ────────────────────────
        print("Step 7: Reviewing verification result...")
        page.keyboard.press("End")
        page.wait_for_timeout(1500)
        screenshot(page, "07_verification_steps")

        # ── Step 8: Push to Jira ──────────────────────────────────────────────
        print("Step 8: Pushing bug to Jira...")
        page.locator("button:has-text('Push to Jira')").first.click()
        page.wait_for_timeout(6000)
        screenshot(page, "08_pushed_to_jira")

        # ── Step 9: Open Jira Tracker ─────────────────────────────────────────
        print("Step 9: Opening Jira Tracker...")
        page.locator("text=Jira Tracker").first.click()
        page.wait_for_timeout(4000)
        screenshot(page, "09_jira_tracker")

        # ── Step 10: Final wide shot ───────────────────────────────────────────
        print("Step 10: Final overview...")
        page.wait_for_timeout(2000)
        screenshot(page, "10_final_overview")

        # Close context to save video
        context.close()
        browser.close()

    # Rename the video
    videos = list(DEMO_DIR.glob("*.webm"))
    if videos:
        final_path = DEMO_DIR / "bug_tracking_agent_demo.webm"
        videos[0].rename(final_path)
        print(f"\n✅ Video saved: {final_path}")
    else:
        print("\n⚠️  No video file found")

    screenshots = sorted(SCREENSHOTS_DIR.glob("*.png"))
    print(f"✅ Screenshots saved: {len(screenshots)} files in demo/screenshots/")
    print("\nFiles ready:")
    print(f"  📹 demo/bug_tracking_agent_demo.webm")
    for s in screenshots:
        print(f"  📸 {s}")
    print("\nDone! Add these to your repo and update README.md")


if __name__ == "__main__":
    run_demo()
