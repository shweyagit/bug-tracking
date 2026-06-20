"""Entry point for the ARQ worker process."""
from app.worker.jobs import WorkerSettings

# ARQ picks this up automatically when run with:
# python -m arq app.worker.main.WorkerSettings
