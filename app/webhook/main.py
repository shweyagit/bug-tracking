import logging

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.webhook.routes.github import router as github_router

logging.basicConfig(level=logging.INFO)
log = structlog.get_logger()

app = FastAPI(
    title="Bug Tracking Agent — Webhook Service",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(github_router, prefix="/webhooks")


@app.get("/health")
async def health():
    return {"status": "ok"}
