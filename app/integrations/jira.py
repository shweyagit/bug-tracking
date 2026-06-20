from base64 import b64encode
from typing import Optional

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from app.config import settings


class JiraClient:
    def __init__(self):
        token = b64encode(
            f"{settings.JIRA_EMAIL}:{settings.JIRA_API_TOKEN}".encode()
        ).decode()
        self.headers = {
            "Authorization": f"Basic {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        self.base_url = settings.JIRA_BASE_URL.rstrip("/")

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def create_issue(self, payload: dict) -> dict:
        async with httpx.AsyncClient(headers=self.headers, timeout=30) as client:
            resp = await client.post(
                f"{self.base_url}/rest/api/3/issue",
                json=payload,
            )
            resp.raise_for_status()
            return resp.json()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def get_issue(self, issue_key: str) -> dict:
        async with httpx.AsyncClient(headers=self.headers, timeout=30) as client:
            resp = await client.get(f"{self.base_url}/rest/api/3/issue/{issue_key}")
            resp.raise_for_status()
            return resp.json()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def search_issues(self, jql: str, fields: list[str] = None) -> list[dict]:
        params = {"jql": jql, "maxResults": 100}
        if fields:
            params["fields"] = ",".join(fields)
        async with httpx.AsyncClient(headers=self.headers, timeout=30) as client:
            resp = await client.get(
                f"{self.base_url}/rest/api/3/search",
                params=params,
            )
            resp.raise_for_status()
            return resp.json().get("issues", [])

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def attach_file(self, issue_key: str, file_bytes: bytes, filename: str) -> dict:
        """Attach a file (image/video) to a Jira issue."""
        headers = {k: v for k, v in self.headers.items() if k != "Content-Type"}
        headers["X-Atlassian-Token"] = "no-check"
        async with httpx.AsyncClient(headers=headers, timeout=60) as client:
            resp = await client.post(
                f"{self.base_url}/rest/api/3/issue/{issue_key}/attachments",
                files={"file": (filename, file_bytes)},
            )
            resp.raise_for_status()
            return resp.json()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def get_project_issues(
        self, project_key: str, status_filter: str = "open"
    ) -> list[dict]:
        """Fetch live issues from Jira board."""
        status_jql = {
            "open": 'statusCategory != Done',
            "all": '',
            "done": 'statusCategory = Done',
        }.get(status_filter, 'statusCategory != Done')

        jql = f'project = {project_key}'
        if status_jql:
            jql += f' AND {status_jql}'
        jql += ' ORDER BY created DESC'

        async with httpx.AsyncClient(headers=self.headers, timeout=30) as client:
            resp = await client.post(
                f"{self.base_url}/rest/api/3/search/jql",
                json={
                    "jql": jql,
                    "maxResults": 100,
                    "fields": ["summary", "status", "priority", "labels", "assignee", "created", "updated", "issuetype"],
                },
            )
            resp.raise_for_status()
            return resp.json().get("issues", [])

    def build_manual_bug_payload(
        self,
        title: str,
        description: str,
        steps_to_reproduce: list[str],
        expected_behaviour: str,
        actual_behaviour: str,
        priority: str,
        labels: list[str],
        affected_feature: str,
    ) -> dict:
        priority_map = {"critical": "Highest", "high": "High", "medium": "Medium", "low": "Low"}
        steps_text = "\n".join(f"{i+1}. {s}" for i, s in enumerate(steps_to_reproduce))

        body_text = (
            f"Description\n{description}\n\n"
            f"Steps to Reproduce\n{steps_text}\n\n"
            f"Expected Behaviour\n{expected_behaviour}\n\n"
            f"Actual Behaviour\n{actual_behaviour}\n\n"
            f"Affected Feature\n{affected_feature}"
        )

        return {
            "fields": {
                "project": {"key": settings.JIRA_PROJECT_KEY},
                "summary": title,
                "description": {
                    "type": "doc",
                    "version": 1,
                    "content": [
                        {
                            "type": "paragraph",
                            "content": [{"type": "text", "text": body_text}],
                        }
                    ],
                },
                "issuetype": {"name": "Bug"},
                "priority": {"name": priority_map.get(priority, "Medium")},
                "labels": [l.replace(" ", "-") for l in labels] + ["bug-agent"],
            }
        }

    def build_bug_payload(
        self,
        title: str,
        summary: str,
        root_cause: str,
        severity: str,
        affected_feature: str,
        github_run_url: str,
        failing_tests: list[str],
        commit_sha: str,
        branch: str,
        pr_title: Optional[str] = None,
    ) -> dict:
        priority_map = {
            "critical": "Highest",
            "high": "High",
            "medium": "Medium",
            "low": "Low",
        }

        description_text = (
            f"*Summary*\n{summary}\n\n"
            f"*Root Cause Hypothesis*\n{root_cause}\n\n"
            f"*Affected Feature*\n{affected_feature}\n\n"
            f"*Failing Tests*\n"
            + "\n".join(f"- {t}" for t in failing_tests)
            + f"\n\n*GitHub Details*\n"
            f"- Branch: {branch}\n"
            f"- Commit: {commit_sha[:8]}\n"
            f"- Run: {github_run_url}\n"
            + (f"- PR: {pr_title}\n" if pr_title else "")
        )

        return {
            "fields": {
                "project": {"key": settings.JIRA_PROJECT_KEY},
                "summary": title,
                "description": {
                    "type": "doc",
                    "version": 1,
                    "content": [
                        {
                            "type": "paragraph",
                            "content": [{"type": "text", "text": description_text}],
                        }
                    ],
                },
                "issuetype": {"name": "Bug"},
                "priority": {"name": priority_map.get(severity, "Medium")},
                "labels": [affected_feature.replace(" ", "_"), "automated-bug-agent"],
            }
        }


jira_client = JiraClient()
