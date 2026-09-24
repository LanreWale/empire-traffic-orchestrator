"""
Pinterest API v5 client.

Two modes controlled by PINTEREST_API_MODE env var:
    sandbox     → api-sandbox.pinterest.com (default while Trial access pending)
    production  → api.pinterest.com       (set after Standard access approved)

Set in .env:
    PINTEREST_API_MODE=production
"""

import os
import requests
from dotenv import load_dotenv

load_dotenv()

_MODE = os.environ.get("PINTEREST_API_MODE", "sandbox").lower()
_BASE = (
    "https://api-sandbox.pinterest.com/v5"
    if _MODE == "sandbox"
    else "https://api.pinterest.com/v5"
)

API_BASE = _BASE


def _headers() -> dict:
    token = os.environ["PINTEREST_ACCESS_TOKEN"]
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }


def list_boards() -> list[dict]:
    """Return all boards for the authenticated account."""
    r = requests.get(f"{API_BASE}/boards", headers=_headers(), timeout=30)
    r.raise_for_status()
    return r.json().get("items", [])


def create_pin(
    board_id: str,
    title: str,
    description: str,
    link: str,
    image_url: str,
    alt_text: str = "",
) -> dict:
    """
    Create a pin on the given board.

    Raises requests.HTTPError on non-2xx. The caller is expected to catch
    this and translate status codes into user-facing errors (e.g. 403 for
    Trial access limitation).
    """
    body: dict = {
        "board_id": board_id,
        "title": title[:100],
        "description": description[:500],
        "link": link,
        "media_source": {
            "source_type": "image_url",
            "url": image_url,
        },
    }

    if alt_text:
        body["alt_text"] = alt_text[:500]

    r = requests.post(
        f"{API_BASE}/pins",
        headers=_headers(),
        json=body,
        timeout=30,
    )
    r.raise_for_status()
    return r.json()
