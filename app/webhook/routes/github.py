import hashlib
import hmac
import logging

from arq import create_pool
from arq.connections import RedisSettings
from fastapi import APIRouter, Header, HTTPException, Request, status

from app.config import settings

router = APIRouter()
logger = logging.getLogger(__name__)


def _verify_signature(payload: bytes, signature: str) -> bool:
    """Validate GitHub HMAC-SHA256 webhook signature."""
    if not signature or not signature.startswith("sha256="):
        return False
    expected = hmac.new(
        settings.GITHUB_WEBHOOK_SECRET.encode(),
        payload,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(f"sha256={expected}", signature)


@router.post("/github")
async def github_webhook(
    request: Request,
    x_hub_signature_256: str = Header(default=""),
    x_github_event: str = Header(default=""),
):
    payload = await request.body()

    if not _verify_signature(payload, x_hub_signature_256):
        logger.warning("Invalid GitHub webhook signature")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid webhook signature",
        )

    if x_github_event != "workflow_run":
        # Accept but ignore non-workflow_run events
        return {"accepted": False, "reason": f"event '{x_github_event}' not handled"}

    body = await request.json() if not hasattr(request, "_json") else request._json
    # Re-parse since we already read the body
    import json
    body = json.loads(payload)

    action = body.get("action", "")
    workflow_run = body.get("workflow_run", {})
    run_id: int = workflow_run.get("id")
    conclusion = workflow_run.get("conclusion")

    logger.info(f"GitHub event: workflow_run action={action} run_id={run_id} conclusion={conclusion}")

    # Only process completed runs with failures
    if action != "completed":
        return {"accepted": False, "reason": "not completed yet"}

    if conclusion not in ("failure", "action_required"):
        return {"accepted": False, "reason": f"conclusion '{conclusion}' does not indicate failure"}

    # Enqueue the processing job
    redis = await create_pool(RedisSettings.from_dsn(settings.REDIS_URL))
    await redis.enqueue_job("process_workflow_run", run_id)
    await redis.aclose()

    logger.info(f"Enqueued job for run {run_id}")
    return {"accepted": True, "run_id": run_id}
