"""Instagram Graph API — Business Discovery (public metrics of other business/creator accounts).

Requires your own Instagram Business/Creator account linked to a Facebook Page and a Meta app token
with instagram_basic + pages_read_engagement. Docs: developers.facebook.com/docs/instagram-api/guides/business-discovery
"""
import httpx

from ..store import get_secret, log_event
from ..util import StageError

BASE = "https://graph.facebook.com/v21.0"


def configured():
    return bool(get_secret("INSTAGRAM_ACCESS_TOKEN") and get_secret("INSTAGRAM_BUSINESS_ID"))


def business_discovery(username, media_limit=12):
    token, me = get_secret("INSTAGRAM_ACCESS_TOKEN"), get_secret("INSTAGRAM_BUSINESS_ID")
    if not (token and me):
        raise StageError("Instagram Graph API is not configured.")
    fields = (f"business_discovery.username({username}){{username,name,followers_count,media_count,"
              f"media.limit({media_limit}){{caption,like_count,comments_count,timestamp,permalink,media_type}}}}")
    r = httpx.get(f"{BASE}/{me}", params={"fields": fields, "access_token": token}, timeout=30)
    if r.status_code != 200:
        log_event("instagram", "error", False, f"{username}: {r.text[:300]}")
        raise StageError(f"Instagram API error: {r.json().get('error', {}).get('message', r.text[:200])}")
    log_event("instagram", "call", True, f"business_discovery {username}")
    bd = r.json().get("business_discovery", {})
    media = []
    for m in (bd.get("media") or {}).get("data", []):
        media.append({"platform": "Instagram", "url": m.get("permalink"), "title": (m.get("caption") or "")[:140],
                      "likes": m.get("like_count"), "comments": m.get("comments_count"),
                      "views": None, "published_at": m.get("timestamp"), "verification": "verified",
                      "source": "Instagram Graph API"})
    return {"platform": "Instagram", "name": bd.get("name") or username, "handle": bd.get("username"),
            "url": f"https://www.instagram.com/{bd.get('username', username)}/",
            "followers": bd.get("followers_count"), "media_count": bd.get("media_count"), "videos": media}


def test():
    token, me = get_secret("INSTAGRAM_ACCESS_TOKEN"), get_secret("INSTAGRAM_BUSINESS_ID")
    r = httpx.get(f"{BASE}/{me}", params={"fields": "username,followers_count", "access_token": token}, timeout=20)
    if r.status_code != 200:
        raise StageError(f"Instagram returned {r.status_code}: {r.text[:200]}")
    return f"Connected as @{r.json().get('username')}."
