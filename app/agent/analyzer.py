import json
from dataclasses import dataclass
from typing import Optional

import anthropic

from app.config import settings

client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)


MANUAL_BUG_PROMPT = """You are a senior QA engineer. A team member has reported a bug in plain English.
Convert it into a structured, professional bug report.

Bug description from team member:
\"\"\"{description}\"\"\"

Project: {project}

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
- steps_to_reproduce must be concrete, numbered steps
- priority: critical=data loss/app crash, high=major feature broken, medium=degraded UX, low=minor/cosmetic
- labels: use kebab-case, max 3 labels
- Keep everything concise and actionable"""


@dataclass
class ManualBugReport:
    title: str
    description: str
    steps_to_reproduce: list[str]
    expected_behaviour: str
    actual_behaviour: str
    priority: str
    labels: list[str]
    affected_feature: str


def analyze_manual_bug(description: str, project: str = "SportIQ") -> ManualBugReport:
    """Convert plain English bug description into a structured bug report."""
    prompt = MANUAL_BUG_PROMPT.format(description=description, project=project)

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
    raw = raw.strip()

    data = json.loads(raw)
    return ManualBugReport(
        title=data["title"],
        description=data["description"],
        steps_to_reproduce=data.get("steps_to_reproduce", []),
        expected_behaviour=data.get("expected_behaviour", ""),
        actual_behaviour=data.get("actual_behaviour", ""),
        priority=data["priority"],
        labels=data.get("labels", []),
        affected_feature=data.get("affected_feature", ""),
    )


@dataclass
class FailedTest:
    name: str
    classname: str
    feature_area: str
    error_message: str
    error_type: str
    stack_trace: str
    consecutive_failures: int = 0


@dataclass
class BugAnalysis:
    title: str
    summary: str
    root_cause: str
    severity: str          # critical | high | medium | low
    affected_feature: str
    suggested_labels: list[str]


ANALYSIS_PROMPT = """You are a senior QA engineer analyzing automated test failures.

You will be given a list of failing tests from a CI run. Analyze them and produce a structured bug report.

## Run Context
- Repository: {repo}
- Branch: {branch}
- Commit: {commit_sha}
- Commit message: {commit_message}
- PR: {pr_title}

## Failing Tests
{failing_tests}

## Instructions
1. Group related failures by root cause if possible.
2. Write a concise bug title (max 100 chars) that captures the core issue.
3. Write a 2-4 sentence summary explaining what broke and the user impact.
4. Hypothesize the most likely root cause based on the error messages and stack traces.
5. Determine severity:
   - critical: core functionality broken, data loss possible, or >50% tests failing
   - high: major feature broken, significant user impact
   - medium: feature degraded but workaround exists
   - low: edge case, cosmetic, or minor impact
6. Identify the primary affected feature area.
7. Suggest 2-4 labels for the Jira ticket.

Respond ONLY with valid JSON in this exact schema:
{{
  "title": "string",
  "summary": "string",
  "root_cause": "string",
  "severity": "critical|high|medium|low",
  "affected_feature": "string",
  "suggested_labels": ["string"]
}}"""


async def analyze_failures(
    failed_tests: list[FailedTest],
    repo: str,
    branch: str,
    commit_sha: str,
    commit_message: str = "",
    pr_title: Optional[str] = None,
) -> BugAnalysis:
    tests_text = ""
    for i, t in enumerate(failed_tests, 1):
        recurring = f" [RECURRING: {t.consecutive_failures} consecutive failures]" if t.consecutive_failures > 1 else ""
        tests_text += (
            f"\n### Test {i}{recurring}\n"
            f"Name: {t.name}\n"
            f"Class: {t.classname}\n"
            f"Feature Area: {t.feature_area}\n"
            f"Error Type: {t.error_type}\n"
            f"Error Message: {t.error_message}\n"
            f"Stack Trace:\n{t.stack_trace[:1000] if t.stack_trace else 'N/A'}\n"
        )

    prompt = ANALYSIS_PROMPT.format(
        repo=repo,
        branch=branch,
        commit_sha=commit_sha[:8] if commit_sha else "unknown",
        commit_message=commit_message or "N/A",
        pr_title=pr_title or "N/A",
        failing_tests=tests_text,
    )

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = message.content[0].text.strip()

    # Strip markdown code fences if present
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    raw = raw.strip()

    data = json.loads(raw)

    return BugAnalysis(
        title=data["title"],
        summary=data["summary"],
        root_cause=data["root_cause"],
        severity=data["severity"],
        affected_feature=data["affected_feature"],
        suggested_labels=data.get("suggested_labels", []),
    )
