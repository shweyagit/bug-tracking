"""
ARQ background jobs — process GitHub Actions workflow run events.
"""
import logging
from datetime import datetime, timezone
from typing import Optional

from arq.connections import RedisSettings, create_pool
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.agent.analyzer import FailedTest, analyze_failures
from app.config import settings
from app.db.models import Bug, FailureStat, TestCase, TestResult, TestRun
from app.db.session import AsyncSessionLocal
from app.integrations.github import github_client
from app.worker.junit_parser import parse_junit_xml

logger = logging.getLogger(__name__)


async def process_workflow_run(ctx: dict, run_id: int):
    """
    Main job: triggered by GitHub webhook.
    Downloads JUnit XML artifacts, parses results,
    updates DB, and triggers AI analysis if failures exist.
    """
    logger.info(f"Processing workflow run {run_id}")

    # 1. Fetch run metadata from GitHub
    run_data = await github_client.get_workflow_run(run_id)

    if run_data.get("conclusion") not in ("failure", "action_required"):
        logger.info(f"Run {run_id} concluded with '{run_data.get('conclusion')}' — skipping analysis")

    repo = run_data["repository"]["full_name"]
    head_commit = run_data.get("head_commit") or {}
    head_sha = run_data.get("head_sha", "")
    branch = run_data.get("head_branch", "")
    pr_number = None
    pr_title = None

    pull_requests = run_data.get("pull_requests", [])
    if pull_requests:
        pr_number = pull_requests[0].get("number")
        pr_title = pull_requests[0].get("head", {}).get("ref")

    async with AsyncSessionLocal() as db:
        # 2. Upsert TestRun record
        existing = await db.execute(
            select(TestRun).where(TestRun.github_run_id == run_id)
        )
        test_run = existing.scalar_one_or_none()

        if not test_run:
            test_run = TestRun(
                github_run_id=run_id,
                github_repo=repo,
                branch=branch,
                commit_sha=head_sha,
                commit_message=head_commit.get("message", ""),
                pr_number=pr_number,
                pr_title=pr_title,
                triggered_by=run_data.get("triggering_actor", {}).get("login", ""),
                workflow_name=run_data.get("name", ""),
                status=run_data.get("status", ""),
                conclusion=run_data.get("conclusion", ""),
                started_at=_parse_dt(run_data.get("run_started_at")),
                completed_at=_parse_dt(run_data.get("updated_at")),
            )
            db.add(test_run)
            await db.flush()
        else:
            test_run.status = run_data.get("status", test_run.status)
            test_run.conclusion = run_data.get("conclusion", test_run.conclusion)
            test_run.completed_at = _parse_dt(run_data.get("updated_at"))

        # 3. Download and parse JUnit XML artifacts
        xml_files = await github_client.get_junit_xml_files(run_id)
        if not xml_files:
            logger.warning(f"No JUnit XML artifacts found for run {run_id}")
            await db.commit()
            return

        all_parsed = []
        for filename, xml_content in xml_files:
            parsed = parse_junit_xml(xml_content, suite_name=filename)
            all_parsed.extend(parsed)

        logger.info(f"Parsed {len(all_parsed)} test results for run {run_id}")

        # 4. Upsert test cases and save results
        failed_tests: list[FailedTest] = []

        for result in all_parsed:
            # Upsert TestCase
            stmt = pg_insert(TestCase).values(
                name=result.name,
                classname=result.classname,
                feature_area=result.feature_area,
                suite_name=result.suite_name,
            ).on_conflict_do_nothing(index_elements=["name", "classname"])
            await db.execute(stmt)

            # Fetch the case
            case_result = await db.execute(
                select(TestCase).where(
                    TestCase.name == result.name,
                    TestCase.classname == result.classname,
                )
            )
            case = case_result.scalar_one_or_none()
            if not case:
                continue

            # Save test result
            tr = TestResult(
                run_id=test_run.id,
                case_id=case.id,
                status=result.status,
                duration_seconds=result.duration_seconds,
                error_message=result.error_message,
                error_type=result.error_type,
                stack_trace=result.stack_trace,
            )
            db.add(tr)

            # Update failure stats
            await _update_failure_stat(db, case, result.status, test_run.completed_at)

            # Collect failures for analysis
            if result.status in ("failed", "error"):
                stat_result = await db.execute(
                    select(FailureStat).where(FailureStat.case_id == case.id)
                )
                stat = stat_result.scalar_one_or_none()
                consecutive = stat.consecutive_failures if stat else 0

                failed_tests.append(
                    FailedTest(
                        name=result.name,
                        classname=result.classname,
                        feature_area=result.feature_area,
                        error_message=result.error_message or "",
                        error_type=result.error_type or "",
                        stack_trace=result.stack_trace or "",
                        consecutive_failures=consecutive,
                    )
                )

        await db.commit()

        # 5. If there are failures, run AI analysis and create bug draft
        if failed_tests:
            logger.info(f"Analyzing {len(failed_tests)} failures for run {run_id}")
            github_run_url = run_data.get("html_url", "")

            analysis = await analyze_failures(
                failed_tests=failed_tests,
                repo=repo,
                branch=branch,
                commit_sha=head_sha,
                commit_message=head_commit.get("message", ""),
                pr_title=pr_title,
            )

            bug = Bug(
                run_id=test_run.id,
                title=analysis.title,
                summary=analysis.summary,
                root_cause=analysis.root_cause,
                affected_feature=analysis.affected_feature,
                severity=analysis.severity,
                failing_test_ids=[str(t.name) for t in failed_tests],
                status="draft",
            )
            db.add(bug)
            await db.commit()

            logger.info(f"Bug draft created for run {run_id}: {analysis.title}")
        else:
            logger.info(f"No failures found for run {run_id}")


async def _update_failure_stat(db, case: TestCase, status: str, run_time):
    """Upsert failure stats for a test case."""
    result = await db.execute(
        select(FailureStat).where(FailureStat.case_id == case.id)
    )
    stat = result.scalar_one_or_none()

    if not stat:
        stat = FailureStat(
            case_id=case.id,
            feature_area=case.feature_area,
            total_runs=0,
            failure_count=0,
            consecutive_failures=0,
        )
        db.add(stat)

    stat.total_runs += 1
    if status in ("failed", "error"):
        stat.failure_count += 1
        stat.consecutive_failures += 1
        stat.last_failed_at = run_time
    else:
        stat.consecutive_failures = 0
        if status == "passed":
            stat.last_passed_at = run_time


def _parse_dt(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


# ARQ worker settings
class WorkerSettings:
    functions = [process_workflow_run]
    redis_settings = RedisSettings.from_dsn(settings.REDIS_URL)
    max_jobs = 10
    job_timeout = 600   # 10 minutes
    keep_result = 3600  # keep job result for 1 hour
