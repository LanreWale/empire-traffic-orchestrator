"""
Shared Supabase client for all channel posters.

Reads and writes the distribution_content table — the queue that the
Empire admin dashboard displays. Use this to fetch what's ready to post
and to report back what happened.

Also re-exports the existing src.supabase_client helpers so callers can
log to posts_tracking (the audit table) alongside the queue.
"""

import os
import sys
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

_client: Client | None = None


def get_supabase() -> Client:
    """Lazy singleton — same pattern as src/supabase_client.py."""
    global _client
    if _client is None:
        url = os.environ["SUPABASE_URL"]
        # Prefer service role key for write access; fall back to anon for read-only.
        key = (
            os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
            or os.environ.get("SUPABASE_KEY")
        )
        if not key:
            print(
                "ERROR: Neither SUPABASE_SERVICE_ROLE_KEY nor SUPABASE_KEY is set.",
                file=sys.stderr,
            )
            print(
                "       Get the service_role key from Supabase → Project Settings → API.",
                file=sys.stderr,
            )
            sys.exit(1)
        _client = create_client(url, key)
    return _client


# ==========================================
# READ
# ==========================================
def fetch_ready(channel: str) -> list:
    """All rows with status='ready' for a channel, oldest first."""
    res = (
        get_supabase()
        .table("distribution_content")
        .select("*")
        .eq("channel", channel)
        .eq("status", "ready")
        .order("created_at")
        .execute()
    )
    return res.data or []


def fetch_by_status(channel: str, status: str) -> list:
    """Rows for a channel filtered by status."""
    res = (
        get_supabase()
        .table("distribution_content")
        .select("*")
        .eq("channel", channel)
        .eq("status", status)
        .order("created_at")
        .execute()
    )
    return res.data or []


# ==========================================
# WRITE — STATE TRANSITIONS
# ==========================================
def mark_queued(row_id: str) -> None:
    get_supabase().table("distribution_content").update({
        "status": "queued",
        "error_message": None,
    }).eq("id", row_id).execute()


def mark_posted(row_id: str, external_id: str) -> None:
    from datetime import datetime, timezone
    get_supabase().table("distribution_content").update({
        "status": "posted",
        "external_id": str(external_id),
        "posted_at": datetime.now(timezone.utc).isoformat(),
        "error_message": None,
    }).eq("id", row_id).execute()


def mark_failed(row_id: str, error: str) -> None:
    get_supabase().table("distribution_content").update({
        "status": "failed",
        "error_message": (error or "Unknown error")[:500],
    }).eq("id", row_id).execute()


def reset_to_ready(row_id: str) -> None:
    get_supabase().table("distribution_content").update({
        "status": "ready",
        "error_message": None,
    }).eq("id", row_id).execute()


def reset_channel_failed_to_ready(channel: str) -> int:
    """Bulk reset: all failed rows for a channel back to ready."""
    rows = fetch_by_status(channel, "failed")
    for row in rows:
        reset_to_ready(row["id"])
    return len(rows)


# ==========================================
# DIAGNOSTICS
# ==========================================
def stats(channel: str) -> dict:
    """Counts per status for a channel."""
    statuses = ["draft", "ready", "queued", "posted", "failed", "manual_required"]
    out = {s: len(fetch_by_status(channel, s)) for s in statuses}
    out["total"] = sum(out.values())
    return out
