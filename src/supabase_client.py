import os
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

_client: Client | None = None


def get_supabase() -> Client:
    global _client
    if _client is None:
        url = os.environ["SUPABASE_URL"]
        key = os.environ["SUPABASE_KEY"]
        _client = create_client(url, key)
    return _client


def log_post(platform: str, offer_id: str, title: str,
             url: str, external_id: str = "", metadata: dict | None = None):
    """Record a posted item to posts_tracking."""
    table = os.environ.get("POSTS_TRACKING_TABLE", "posts_tracking")
    get_supabase().table(table).insert({
        "platform": platform,
        "offer_id": offer_id,
        "external_id": external_id,
        "url": url,
        "title": title,
        "status": "posted",
        "metadata": metadata or {},
    }).execute()


def recently_posted(platform: str, title: str, days: int = 30) -> bool:
    """Check if the same title was posted in the last N days."""
    from datetime import datetime, timedelta, timezone
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    table = os.environ.get("POSTS_TRACKING_TABLE", "posts_tracking")
    res = (
        get_supabase()
        .table(table)
        .select("id")
        .eq("platform", platform)
        .eq("title", title)
        .gte("posted_at", cutoff)
        .limit(1)
        .execute()
    )
    return bool(res.data)