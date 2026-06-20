from base64 import b64encode
from typing import Optional

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from app.config import settings


class TestRailClient:
    """
    Optional TestRail integration.
    Used to enrich bug reports with TestRail case metadata
    or to update test run results back into TestRail.
    """

    def __init__(self):
        token = b64encode(
            f"{settings.TESTRAIL_EMAIL}:{settings.TESTRAIL_API_KEY}".encode()
        ).decode()
        self.headers = {
            "Authorization": f"Basic {token}",
            "Content-Type": "application/json",
        }
        self.base_url = settings.TESTRAIL_BASE_URL.rstrip("/") + "/index.php?/api/v2"

    @property
    def enabled(self) -> bool:
        return bool(settings.TESTRAIL_BASE_URL and settings.TESTRAIL_API_KEY)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def get_case(self, case_id: int) -> Optional[dict]:
        if not self.enabled:
            return None
        async with httpx.AsyncClient(headers=self.headers, timeout=30) as client:
            resp = await client.get(f"{self.base_url}/get_case/{case_id}")
            resp.raise_for_status()
            return resp.json()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def get_tests_for_run(self, run_id: int) -> list[dict]:
        if not self.enabled:
            return []
        async with httpx.AsyncClient(headers=self.headers, timeout=30) as client:
            resp = await client.get(f"{self.base_url}/get_tests/{run_id}")
            resp.raise_for_status()
            return resp.json().get("tests", [])

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def add_result_for_case(
        self, run_id: int, case_id: int, status_id: int, comment: str = ""
    ) -> dict:
        """
        Status IDs: 1=Passed, 2=Blocked, 3=Untested, 4=Retest, 5=Failed
        """
        if not self.enabled:
            return {}
        async with httpx.AsyncClient(headers=self.headers, timeout=30) as client:
            resp = await client.post(
                f"{self.base_url}/add_result_for_case/{run_id}/{case_id}",
                json={"status_id": status_id, "comment": comment},
            )
            resp.raise_for_status()
            return resp.json()


testrail_client = TestRailClient()
