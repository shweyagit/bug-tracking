"""Sync DB helper for Streamlit (uses psycopg2 directly)."""
import os
from contextlib import contextmanager

import psycopg2
import psycopg2.extras


def get_dsn() -> str:
    url = os.getenv("DATABASE_URL", "postgresql://bta:bta_secret@postgres:5432/bug_tracking")
    return url.replace("postgresql+asyncpg://", "postgresql://")


@contextmanager
def get_conn():
    conn = psycopg2.connect(get_dsn())
    try:
        yield conn
    finally:
        conn.close()


def query(sql: str, params=None) -> list[dict]:
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            return [dict(r) for r in cur.fetchall()]


def execute(sql: str, params=None):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
        conn.commit()
