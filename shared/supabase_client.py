"""
Shared Supabase client for all channel posters.

Reads SUPABASE_SERVICE_ROLE_KEY from environment — required because posters
need write access to distribution_content (RLS blocks anon writes).
"""

import os
import sys
from supabase import create_client, Client

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


def fetch_ready(channel: str) -> list:
    """Return all rows with status='ready' for a given channel, oldest first."""
    res = (
        supabase.table("distribution_content")
        .select("*")
        .eq("channel", channel)
        .eq("status", "ready")
        .order("created_at")
        .execute()
    )
    return res.data or []


def mark_queued(row_id: str) -> None:
    supabase.table("distribution_content").update({
        "status": "queued",
        "error_message": None,
    }).eq("id", row_id).execute()


def mark_posted(row_id: str, external_id: str) -> None:
    supabase.table("distribution_content").update({
        "status": "posted",
        "external_id": external_id,
        "posted_at": "now()",
        "error_message": None,
    }).eq("id", row_id).execute()


def mark_failed(row_id: str, error: str) -> None:
    supabase.table("distribution_content").update({
        "status": "failed",
        "error_message": error[:500],
    }).eq("id", row_id).execute()


def mark_manual(row_id: str, note: str = "") -> None:
    supabase.table("distribution_content").update({
        "status": "manual_required",
        "error_message": note[:500] or None,
    }).eq("id", row_id).execute()
