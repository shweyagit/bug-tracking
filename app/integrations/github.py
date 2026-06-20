import zipfile
import io
from typing import Optional

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from app.config import settings


class GitHubClient:
    BASE_URL = "https://api.github.com"

    def __init__(self):
        self.headers = {
            "Authorization": f"Bearer {settings.GITHUB_TOKEN}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def get_workflow_run(self, run_id: int) -> dict:
        repo = settings.GITHUB_REPO
        async with httpx.AsyncClient(headers=self.headers, timeout=30) as client:
            resp = await client.get(f"{self.BASE_URL}/repos/{repo}/actions/runs/{run_id}")
            resp.raise_for_status()
            return resp.json()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def list_run_artifacts(self, run_id: int) -> list[dict]:
        repo = settings.GITHUB_REPO
        async with httpx.AsyncClient(headers=self.headers, timeout=30) as client:
            resp = await client.get(
                f"{self.BASE_URL}/repos/{repo}/actions/runs/{run_id}/artifacts"
            )
            resp.raise_for_status()
            return resp.json().get("artifacts", [])

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def download_artifact_zip(self, artifact_id: int) -> bytes:
        repo = settings.GITHUB_REPO
        # First get the download URL (GitHub returns a redirect)
        async with httpx.AsyncClient(
            headers=self.headers, timeout=60, follow_redirects=True
        ) as client:
            resp = await client.get(
                f"{self.BASE_URL}/repos/{repo}/actions/artifacts/{artifact_id}/zip"
            )
            resp.raise_for_status()
            return resp.content

    async def get_junit_xml_files(self, run_id: int) -> list[tuple[str, str]]:
        """
        Returns list of (filename, xml_content) tuples for all JUnit XML
        artifacts in the given workflow run.
        """
        artifacts = await self.list_run_artifacts(run_id)
        xml_files: list[tuple[str, str]] = []

        for artifact in artifacts:
            # Look for test-report artifacts (adjust naming convention as needed)
            name: str = artifact.get("name", "")
            if not any(kw in name.lower() for kw in ("test", "junit", "report", "result")):
                continue

            zip_bytes = await self.download_artifact_zip(artifact["id"])
            with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
                for entry in zf.namelist():
                    if entry.endswith(".xml"):
                        xml_content = zf.read(entry).decode("utf-8", errors="replace")
                        xml_files.append((entry, xml_content))

        return xml_files

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def get_pull_request(self, pr_number: int) -> Optional[dict]:
        repo = settings.GITHUB_REPO
        async with httpx.AsyncClient(headers=self.headers, timeout=30) as client:
            resp = await client.get(f"{self.BASE_URL}/repos/{repo}/pulls/{pr_number}")
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            return resp.json()


github_client = GitHubClient()
