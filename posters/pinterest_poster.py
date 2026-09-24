"""
Pinterest poster — reads ready pins from Supabase, posts via Pinterest v5 API,
writes results back to distribution_content AND logs to posts_tracking.

Usage:
    python posters/pinterest_poster.py

Environment variables required:
    PINTEREST_ACCESS_TOKEN     — Pinterest v5 token
    PINTEREST_API_MODE         — 'sandbox' (default) or 'production'
    SUPABASE_URL               — Supabase project URL
    SUPABASE_SERVICE_ROLE_KEY  — service role key (write access)

Exit codes:
    0 — success (all pins posted, or nothing to do)
    2 — Pinterest 403 (Trial access blocks production pins)
    3 — partial failure (some pins failed for other reasons)
"""

import os
import sys
import time
from pathlib import Path

# Ensure repo root on path so 'shared' and 'src' both import cleanly
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import requests

from shared.supabase_client import (
    fetch_ready, mark_queued, mark_posted, mark_failed,
    get_supabase,
)
from src.pinterest_client import create_pin, API_BASE


# ==========================================
# AUDIT LOG (posts_tracking)
# ==========================================
def log_to_audit(row: dict, external_id: str) -> None:
    """
    Also record the successful post in posts_tracking (the audit table
    the existing supabase_client.py writes to). Best-effort — failures
    here do not roll back the pin.
    """
    try:
        table = os.environ.get("POSTS_TRACKING_TABLE", "posts_tracking")
        get_supabase().table(table).insert({
            "platform": "pinterest",
            "offer_id": row.get("offer_id") or "",
            "external_id": external_id,
            "url": row["destination_url"],
            "title": row.get("title") or "",
            "status": "posted",
            "metadata": {
                "board_id": row.get("metadata", {}).get("board_id"),
                "board_or_target": row.get("board_or_target"),
                "dist_id": row["id"],
            },
        }).execute()
    except Exception as e:
        print(f"    ⚠ audit log write failed (non-fatal): {e}")


# ==========================================
# SINGLE PIN
# ==========================================
def post_one(row: dict) -> tuple[bool, str | None]:
    """
    Post a single row. Returns (ok, external_id_or_error).
    Handles the 403 case specially so the caller can stop early.
    """
    board_id = row.get("metadata", {}).get("board_id")
    if not board_id:
        return False, "Missing board_id in metadata"

    image_url = row.get("media_url")
    if not image_url:
        return False, "Missing media_url"

    try:
        result = create_pin(
            board_id=board_id,
            title=row.get("title") or "",
            description=row.get("description") or "",
            link=row["destination_url"],
            image_url=image_url,
            alt_text=row.get("metadata", {}).get("alt_text", ""),
        )
    except requests.HTTPError as e:
        status = e.response.status_code if e.response is not None else 0
        detail = ""
        if e.response is not None:
            detail = e.response.text[:300]
        if status == 403:
            return False, f"403 Forbidden — Trial access blocks production pins. {detail}"
        if status == 401:
            return False, f"401 Unauthorized — check PINTEREST_ACCESS_TOKEN. {detail}"
        if status == 429:
            return False, f"429 Rate limited — slow down and retry. {detail}"
        return False, f"{status} {detail}"
    except requests.RequestException as e:
        return False, f"Network error: {e}"

    pin_id = result.get("id", "")
    return True, pin_id


# ==========================================
# MAIN
# ==========================================
def main() -> int:
    print("=" * 60)
    print("  Pinterest Poster — Empire Traffic Orchestrator")
    print(f"  API mode: {API_BASE}")
    print("=" * 60)
    print()

    rows = fetch_ready("pinterest")
    total = len(rows)

    if total == 0:
        print("No ready pins in distribution_content. Nothing to do.")
        return 0

    print(f"Found {total} ready pin(s).")
    print()

    success = 0
    failed = 0
    trial_blocked = False

    for i, row in enumerate(rows, start=1):
        title = (row.get("title") or "(untitled)")[:60]
        board = row.get("board_or_target") or "?"
        print(f"[{i}/{total}] {board} → {title}")

        mark_queued(row["id"])

        ok, result = post_one(row)

        if ok:
            mark_posted(row["id"], result)
            log_to_audit(row, result)
            print(f"    ✓ Posted. Pinterest pin id: {result}")
            success += 1
        else:
            mark_failed(row["id"], result)
            print(f"    ✗ {result}")
            if "403" in (result or ""):
                trial_blocked = True
                print("      (Trial access blocks pin creation — expected until Standard is approved.)")
                break
            failed += 1

        time.sleep(1.2)  # rate-limit courtesy

    # -------- SUMMARY --------
    print()
    print("=" * 60)
    print(f"  Posted:  {success}")
    print(f"  Failed:  {failed}")

    if trial_blocked:
        print()
        print("  ⚠ Trial access is blocking posting.")
        print("    Once Standard access is approved:")
        print("      1. Set PINTEREST_API_MODE=production in .env")
        print("      2. Regenerate PINTEREST_ACCESS_TOKEN")
        print("      3. Reset failed pins:")
        print("         UPDATE distribution_content")
        print("         SET status='ready', error_message=NULL")
        print("         WHERE channel='pinterest' AND status='failed';")
        print("      4. Re-run this script.")
        print("=" * 60)
        return 2

    print("=" * 60)
    return 0 if failed == 0 else 3


if __name__ == "__main__":
    sys.exit(main())
