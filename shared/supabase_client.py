"""
Shared Supabase client for all channel posters.

Reads SUPABASE_SERVICE_ROLE_KEY from environment — required because posters
need write access to distribution_content (RLS blocks anon writes).

Usage (from any poster script):
    import sys, os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from shared.supabase_client import (
        fetch_ready, mark_queued, mark_posted, mark_failed, mark_manual,
    )

Environment variables required:
    SUPABASE_SERVICE_ROLE_KEY   — service role key (write access)
    SUPABASE_URL                — optional, defaults to the Empire project URL
"""

import os
import sys
from supabase import create_client, Client

# ==========================================
# CONFIG
# ==========================================
SUPABASE_URL = os.environ.get(
    "SUPABASE_URL",
    "https://qujlyrmatuvlpoeheqgf.supabase.co"
)
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")

if not SUPABASE_KEY:
    print("ERROR: SUPABASE_SERVICE_ROLE_KEY environment variable not set.", file=sys.stderr)
    print("", file=sys.stderr)
    print("Get it from: Supabase Dashboard → Project Settings → API → service_role key", file=sys.stderr)
    print("", file=sys.stderr)
    print("PowerShell (current session):", file=sys.stderr)
    print("  $env:SUPABASE_SERVICE_ROLE_KEY = 'eyJ...'", file=sys.stderr)
    print("", file=sys.stderr)
    print("PowerShell (persistent):", file=sys.stderr)
    print("  [Environment]::SetEnvironmentVariable('SUPABASE_SERVICE_ROLE_KEY', 'eyJ...', 'User')", file=sys.stderr)
    sys.exit(1)

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


# ==========================================
# READ
# ==========================================
def fetch_ready(channel: str) -> list:
    """
    Return all rows with status='ready' for a given channel, oldest first.

    Args:
        channel: 'pinterest' | 'telegram' | 'quora' | 'reddit' | 'youtube'
                 | 'twitter' | 'instagram' | 'tiktok' | 'linkedin'

    Returns:
        List of row dicts from distribution_content.
    """
    res = (
        supabase.table("distribution_content")
        .select("*")
        .eq("channel", channel)
        .eq("status", "ready")
        .order("created_at")
        .execute()
    )
    return res.data or []


def fetch_by_status(channel: str, status: str) -> list:
    """Return rows for a channel filtered by arbitrary status."""
    res = (
        supabase.table("distribution_content")
        .select("*")
        .eq("channel", channel)
        .eq("status", status)
        .order("created_at")
        .execute()
    )
    return res.data or []


def fetch_one(row_id: str) -> dict | None:
    """Fetch a single row by id. Returns None if not found."""
    res = (
        supabase.table("distribution_content")
        .select("*")
        .eq("id", row_id)
        .limit(1)
        .execute()
    )
    return (res.data or [None])[0]


# ==========================================
# WRITE — STATE TRANSITIONS
# ==========================================
def mark_queued(row_id: str) -> None:
    """Set status='queued' — poster has picked it up and is about to publish."""
    supabase.table("distribution_content").update({
        "status": "queued",
        "error_message": None,
    }).eq("id", row_id).execute()


def mark_posted(row_id: str, external_id: str) -> None:
    """
    Set status='posted' with the platform's returned ID.

    Args:
        row_id:      distribution_content.id
        external_id: Pinterest pin id / Telegram message id / Reddit post id / etc.
    """
    supabase.table("distribution_content").update({
        "status": "posted",
        "external_id": str(external_id),
        "posted_at": "now()",
        "error_message": None,
    }).eq("id", row_id).execute()


def mark_failed(row_id: str, error: str) -> None:
    """Set status='failed' with a truncated error message (max 500 chars)."""
    supabase.table("distribution_content").update({
        "status": "failed",
        "error_message": (error or "Unknown error")[:500],
    }).eq("id", row_id).execute()


def mark_manual(row_id: str, note: str = "") -> None:
    """
    Set status='manual_required' — for channels without an API (e.g. Quora),
    or when a human needs to intervene.
    """
    supabase.table("distribution_content").update({
        "status": "manual_required",
        "error_message": (note or None),
    }).eq("id", row_id).execute()


def reset_to_ready(row_id: str) -> None:
    """Reset a failed row back to ready — for retries after fixing the cause."""
    supabase.table("distribution_content").update({
        "status": "ready",
        "error_message": None,
    }).eq("id", row_id).execute()


def reset_channel_to_ready(channel: str) -> int:
    """
    Bulk reset: all failed rows for a channel back to ready.
    Returns the number of rows affected.

    Useful when Trial access blocks posting and you want to retry later:

        from shared.supabase_client import reset_channel_to_ready
        count = reset_channel_to_ready("pinterest")
        print(f"Reset {count} pins")
    """
    before = fetch_by_status(channel, "failed")
    for row in before:
        reset_to_ready(row["id"])
    return len(before)


# ==========================================
# DIAGNOSTICS
# ==========================================
def stats(channel: str) -> dict:
    """
    Return counts per status for a channel.
    Handy for poster scripts that want a quick summary line.
    """
    statuses = ["draft", "ready", "queued", "posted", "failed", "manual_required"]
    out = {s: 0 for s in statuses}
    for s in statuses:
        rows = fetch_by_status(channel, s)
        out[s] = len(rows)
    out["total"] = sum(out[s] for s in statuses)
    return out
