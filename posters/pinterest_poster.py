"""
Pinterest pin poster — reads ready pins from Supabase, posts via Pinterest v5 API,
writes results back to distribution_content.

Usage:
    python posters/pinterest_poster.py

Environment variables required:
    PINTEREST_ACCESS_TOKEN   — Pinterest API v5 access token
    SUPABASE_SERVICE_ROLE_KEY — Supabase service role key

Exit codes:
    0 — success (all pins posted, or nothing to do)
    1 — configuration error
    2 — Pinterest auth/access error (likely Trial access — no pins posted)
    3 — partial failure (some pins failed)
"""

import os
import sys
import time
import requests

# Add parent to path so we can import shared
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from shared.supabase_client import (
    fetch_ready, mark_queued, mark_posted, mark_failed, mark_manual,
)

# ==========================================
# CONFIG
# ==========================================
PINTEREST_API = "https://api.pinterest.com/v5"
PINTEREST_TOKEN = os.environ.get("PINTEREST_ACCESS_TOKEN")

if not PINTEREST_TOKEN:
    print("ERROR: PINTEREST_ACCESS_TOKEN not set.", file=sys.stderr)
    print("", file=sys.stderr)
    print("Generate one at: https://developers.pinterest.com/apps/1614635", file=sys.stderr)
    print("", file=sys.stderr)
    print("  $env:PINTEREST_ACCESS_TOKEN = 'pina_...'", file=sys.stderr)
    sys.exit(1)

HEADERS = {
    "Authorization": f"Bearer {PINTEREST_TOKEN}",
    "Content-Type": "application/json",
}

# ==========================================
# PINTEREST API CALL
# ==========================================
def create_pin(row: dict) -> dict:
    """
    POST /v5/pins — create a pin.
    Returns { 'ok': True, 'pin_id': '...' } on success.
    Returns { 'ok': False, 'status': int, 'error': '...' } on failure.
    """
    board_id = row.get("metadata", {}).get("board_id")
    if not board_id:
        return {"ok": False, "status": 0, "error": "Missing board_id in metadata"}

    # Pinterest hard limits — truncate defensively
    title = (row.get("title") or "")[:100]
    description = (row.get("description") or "")[:500]
    alt_text = (row.get("metadata", {}).get("alt_text") or "")[:500]
    image_url = row.get("media_url")

    if not image_url:
        return {"ok": False, "status": 0, "error": "Missing media_url"}

    body = {
        "board_id": board_id,
        "title": title,
        "description": description,
        "alt_text": alt_text,
        "link": row["destination_url"],
        "media_source": {
            "source_type": "image_url",
            "url": image_url,
        },
    }

    try:
        r = requests.post(
            f"{PINTEREST_API}/pins",
            headers=HEADERS,
            json=body,
            timeout=30,
        )
    except requests.RequestException as e:
        return {"ok": False, "status": 0, "error": f"Network error: {e}"}

    # Success
    if r.status_code in (200, 201):
        pin_id = r.json().get("id", "")
        return {"ok": True, "pin_id": pin_id}

    # Known failure modes
    if r.status_code == 401:
        return {"ok": False, "status": 401, "error": "Unauthorized — access token invalid or expired"}
    if r.status_code == 403:
        return {"ok": False, "status": 403, "error": "Forbidden — Trial access cannot create production pins. Standard access required."}
    if r.status_code == 429:
        return {"ok": False, "status": 429, "error": "Rate limited — try again in a few minutes"}

    # Generic
    return {"ok": False, "status": r.status_code, "error": r.text[:300]}


# ==========================================
# MAIN
# ==========================================
def main() -> int:
    print("=" * 60)
    print("  Pinterest Poster — Empire Traffic Orchestrator")
    print("=" * 60)
    print()

    rows = fetch_ready("pinterest")
    total = len(rows)

    if total == 0:
        print("No ready pins in distribution_content. Nothing to do.")
        print()
        return 0

    print(f"Found {total} ready pin(s) to post.")
    print()

    success = 0
    failed = 0
    trial_blocked = False

    for i, row in enumerate(rows, start=1):
        title = (row.get("title") or "(untitled)")[:60]
        board = row.get("board_or_target") or "?"
        print(f"[{i}/{total}] {board} → {title}")

        mark_queued(row["id"])

        result = create_pin(row)

        if result["ok"]:
            pin_id = result["pin_id"]
            mark_posted(row["id"], pin_id)
            print(f"    ✓ Posted. Pinterest pin id: {pin_id}")
            success += 1
        else:
            error = result.get("error", "Unknown error")
            mark_failed(row["id"], error)

            if result.get("status") == 403:
                print(f"    ✗ 403 Forbidden — Trial access blocks pin creation.")
                print(f"      This is expected until Pinterest approves Standard access.")
                trial_blocked = True
                # No point continuing — every pin will fail the same way
                break
            else:
                print(f"    ✗ {error}")
                failed += 1

        # Rate limiting courtesy
        time.sleep(1.2)

    # ==========================================
    # SUMMARY
    # ==========================================
    print()
    print("=" * 60)
    print(f"  Posted:  {success}")
    print(f"  Failed:  {failed}")
    if trial_blocked:
        print()
        print("  ⚠ Trial access is blocking pin creation.")
        print("    All unposted pins have been marked as 'failed' with the 403 message.")
        print("    Once Standard access is approved:")
        print("      1. Regenerate your Pinterest access token")
        print("      2. Reset failed pins back to 'ready' (SQL below)")
        print("      3. Re-run this script")
        print()
        print("    Reset SQL:")
        print("      UPDATE distribution_content")
        print("      SET status='ready', error_message=NULL")
        print("      WHERE channel='pinterest' AND status='failed';")
        print("=" * 60)
        return 2

    print("=" * 60)

    return 0 if failed == 0 else 3


if __name__ == "__main__":
    sys.exit(main())
