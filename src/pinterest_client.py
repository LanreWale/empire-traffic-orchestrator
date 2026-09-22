import os
import requests
from dotenv import load_dotenv

load_dotenv()

API_BASE = "https://api.pinterest.com/v5"


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


def create_pin(board_id: str, title: str, description: str,
               link: str, image_url: str) -> dict:
    """Create a pin on the given board."""
    body = {
        "board_id": board_id,
        "title": title[:100],
        "description": description[:500],
        "link": link,
        "media_source": {
            "source_type": "image_url",
            "url": image_url,
        },
    }
    r = requests.post(
        f"{API_BASE}/pins",
        headers=_headers(),
        json=body,
        timeout=30,
    )
    r.raise_for_status()
    return r.json()