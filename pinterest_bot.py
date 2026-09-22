"""
Empire Traffic Orchestrator — Pinterest Auto-Poster.

Posts pins from config/content_bank.json to Pinterest on a
human-plausible schedule. Logs every pin to Supabase so the
Empire Monitor can track activity.

Usage:
  python pinterest_bot.py --dry-run     preview, no posting
  python pinterest_bot.py --once        post 1 pin, then exit
  python pinterest_bot.py               post N pins (PINS_PER_RUN), then exit
  python pinterest_bot.py --list-boards list boards on the account
"""
from __future__ import annotations
import argparse
import json
import os
import random
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from src.pinterest_client import list_boards, create_pin
from src.supabase_client import log_post, recently_posted

ROOT = Path(__file__).parent
CONFIG = ROOT / "config"

# Placeholder images — real pins need a hosted image per offer.
# For testing, use Pinterest-friendly placeholder URLs.
FALLBACK_IMAGE = (
    "https://images.unsplash.com/photo-1499750310107-5fef28a66643"
    "?w=1000&auto=format&fit=crop"
)


def load_boards() -> dict:
    return json.loads((CONFIG / "boards.json").read_text())


def load_content() -> list[dict]:
    data = json.loads((CONFIG / "content_bank.json").read_text())
    return data.get("pins", [])


def resolve_board_id(slug: str, boards: dict) -> str:
    """Return the numeric board id if set, otherwise fall back to slug."""
    entry = boards.get(slug, {})
    bid = entry.get("board_id", "")
    if bid and bid != "REPLACE_ME_" + str(list(boards).index(slug) + 1):
        return bid
    # Fallback: look up live board list by name
    live = list_boards()
    target_name = entry.get("name", "")
    for b in live:
        if b.get("name") == target_name:
            return str(b["id"])
    raise RuntimeError(
        f"Could not resolve board id for '{slug}'. "
        f"Run --list-boards to verify the board exists."
    )


def pick_unposted(pins: list[dict], count: int) -> list[dict]:
    random.shuffle(pins)
    chosen = []
    for pin in pins:
        if recently_posted("pinterest", pin["title"], days=60):
            continue
        chosen.append(pin)
        if len(chosen) >= count:
            break
    return chosen


def do_post(pin: dict, board_id: str, dry_run: bool = False) -> None:
    tags = " ".join(f"#{t}" for t in pin.get("hashtags", []))
    description = f"{pin['description']}\n\n{tags}"

    if dry_run:
        print(f"[DRY] Would pin '{pin['title']}' → board {board_id}")
        print(f"      link: {pin['link']}")
        return

    result = create_pin(
        board_id=board_id,
        title=pin["title"],
        description=description,
        link=pin["link"],
        image_url=pin.get("image_url", FALLBACK_IMAGE),
    )
    pin_id = result.get("id", "")
    print(f"[POSTED] {pin['title']} → https://pinterest.com/pin/{pin_id}/")

    log_post(
        platform="pinterest",
        offer_id=pin.get("offer_id", ""),
        title=pin["title"],
        url=pin["link"],
        external_id=pin_id,
        metadata={"board_id": board_id, "tags": pin.get("hashtags", [])},
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--list-boards", action="store_true")
    args = ap.parse_args()

    if args.list_boards:
        for b in list_boards():
            print(f"{b['id']}  {b['name']}")
        return

    boards = load_boards()
    content = load_content()

    if not content:
        print("No content in config/content_bank.json")
        sys.exit(1)

    count = 1 if args.once else int(os.environ.get("PINS_PER_RUN", "3"))
    chosen = pick_unposted(content, count)

    if not chosen:
        print("Nothing new to post — all pins were posted recently.")
        return

    print(f"Posting {len(chosen)} pin(s)...\n")

    for i, pin in enumerate(chosen):
        try:
            board_id = resolve_board_id(pin["board"], boards)
            do_post(pin, board_id, dry_run=args.dry_run)
        except Exception as e:
            print(f"[ERROR] {pin['title']}: {e}")

        if i < len(chosen) - 1 and not args.dry_run:
            delay = random.uniform(20, 60)  # human-plausible gap
            print(f"      waiting {delay:.0f}s before next pin...")
            time.sleep(delay)

    print("\nDone.")


if __name__ == "__main__":
    main()