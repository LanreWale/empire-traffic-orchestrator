"""
Empire Traffic Orchestrator — Pinterest Pin Poster
Reads pins.json, posts each 'ready' pin via Pinterest API v5.
Skips pins already posted (tracked in posted_pins.json).
"""

import json
import os
import sys
import time
import requests

# ======================== CONFIG ========================
PINTEREST_API = "https://api.pinterest.com/v5"
PINS_FILE = "pins/pins.json"
POSTED_FILE = "pins/posted_pins.json"

# Read token from environment variable (recommended)
# Or set it directly below (less safe — don't commit to a public repo)
ACCESS_TOKEN = os.environ.get("PINTEREST_ACCESS_TOKEN", "")

if not ACCESS_TOKEN:
    print("ERROR: PINTEREST_ACCESS_TOKEN environment variable not set.")
    print("Set it in PowerShell:  $env:PINTEREST_ACCESS_TOKEN = 'pina_...'")
    sys.exit(1)

# ======================== HELPERS ========================
def load_json(path, default):
    if not os.path.exists(path):
        return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

def create_pin(pin):
    """POST /v5/pins — create a pin on a board."""
    url = f"{PINTEREST_API}/pins"
    headers = {
        "Authorization": f"Bearer {ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }
    body = {
        "board_id": pin["board_id"],
        "title": pin["title"][:100],          # Pinterest max = 100 chars
        "description": pin["description"][:500], # Pinterest max = 500 chars
        "alt_text": pin.get("alt_text", "")[:500],
        "link": pin["link"],
        "media_source": {
            "source_type": "image_url",
            "url": pin["image_url"],
        },
    }
    r = requests.post(url, headers=headers, json=body, timeout=30)
    return r

# ======================== MAIN ========================
def main():
    pins_data = load_json(PINS_FILE, {"pins": []})
    posted = load_json(POSTED_FILE, {"posted_ids": []})
    posted_ids = set(posted.get("posted_ids", []))

    ready_pins = [p for p in pins_data["pins"] if p.get("status") == "ready"]
    pending = [p for p in ready_pins if p["id"] not in posted_ids]

    print(f"Total pins in file : {len(pins_data['pins'])}")
    print(f"Marked ready       : {len(ready_pins)}")
    print(f"Already posted     : {len(posted_ids)}")
    print(f"To post now        : {len(pending)}\n")

    if not pending:
        print("Nothing to post. All ready pins already live.")
        return

    success = 0
    failed = 0

    for pin in pending:
        print(f"→ Posting: {pin['id']}  ({pin['board_name']})")
        try:
            r = create_pin(pin)
        except Exception as e:
            print(f"   ✗ Network error: {e}")
            failed += 1
            continue

        if r.status_code in (200, 201):
            pin_id = r.json().get("id", "unknown")
            print(f"   ✓ Posted. Pinterest pin id: {pin_id}")
            posted_ids.add(pin["id"])
            success += 1
        elif r.status_code == 403:
            print(f"   ✗ 403 Forbidden — likely still on Trial access, or missing pins:write scope.")
            print(f"     Response: {r.text[:300]}")
            failed += 1
            break  # don't spam if scope is wrong
        else:
            print(f"   ✗ {r.status_code}: {r.text[:300]}")
            failed += 1

        time.sleep(1.2)  # be gentle with the API

    # Save updated posted list
    save_json(POSTED_FILE, {"posted_ids": sorted(posted_ids)})

    print(f"\n{'='*40}")
    print(f"Success: {success}")
    print(f"Failed : {failed}")
    print(f"{'='*40}")

if __name__ == "__main__":
    main()
