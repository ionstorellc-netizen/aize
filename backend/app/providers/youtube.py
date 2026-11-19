"""YouTube Data API v3: verified public metrics for research and competitor intelligence."""
from datetime import datetime, timedelta, timezone

import httpx

from ..store import get_secret, log_event
from ..util import StageError

BASE = "https://www.googleapis.com/youtube/v3"
# quota cost per call (YouTube units)
UNITS = {"search": 100, "videos": 1, "channels": 1}


def configured():
    return bool(get_secret("YOUTUBE_API_KEY"))


def _get(endpoint, params, project_id=None):
    key = get_secret("YOUTUBE_API_KEY")
    if not key:
        raise StageError("YouTube Data API is not configured. Add YOUTUBE_API_KEY in Integrations.")
    try:
        r = httpx.get(f"{BASE}/{endpoint}", params={**params, "key": key}, timeout=30)
    except httpx.HTTPError as e:
        log_event("youtube", "error", False, f"{endpoint}: {e}", project_id=project_id)
        raise StageError(f"Could not reach YouTube API: {e}") from e
    if r.status_code != 200:
        msg = r.json().get("error", {}).get("message", r.text[:300]) if r.headers.get("content-type", "").startswith("application/json") else r.text[:300]
        log_event("youtube", "error", False, f"{endpoint}: {r.status_code} {msg}", project_id=project_id)
        raise StageError(f"YouTube API error {r.status_code}: {msg}")
    log_event("youtube", "call", True, endpoint, units=UNITS.get(endpoint, 1), project_id=project_id)
    return r.json()


def search_videos(query, region=None, days=90, max_results=25, short=True, order="viewCount"):
    after = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    params = {"part": "snippet", "q": query, "type": "video", "maxResults": max_results, "order": order,
              "publishedAfter": after}
    if short:
        params["videoDuration"] = "short"
    if region:
        params["regionCode"] = region
    data = _get("search", params)
    return [i["id"]["videoId"] for i in data.get("items", []) if i.get("id", {}).get("videoId")]


def video_details(ids):
    out = []
    for i in range(0, len(ids), 50):
        data = _get("videos", {"part": "snippet,statistics,contentDetails", "id": ",".join(ids[i:i + 50])})
        for v in data.get("items", []):
            st, sn = v.get("statistics", {}), v.get("snippet", {})
            out.append({
                "platform": "YouTube",
                "id": v["id"],
                "url": f"https://www.youtube.com/watch?v={v['id']}",
                "title": sn.get("title", ""),
                "description": (sn.get("description") or "")[:500],
                "channel_id": sn.get("channelId"),
                "channel": sn.get("channelTitle"),
                "published_at": sn.get("publishedAt"),
                "duration": v.get("contentDetails", {}).get("duration"),
                "views": int(st["viewCount"]) if "viewCount" in st else None,
                "likes": int(st["likeCount"]) if "likeCount" in st else None,
                "comments": int(st["commentCount"]) if "commentCount" in st else None,
                "thumbnail": (sn.get("thumbnails", {}).get("high") or sn.get("thumbnails", {}).get("default") or {}).get("url"),
                "tags": sn.get("tags", [])[:15],
                "verification": "verified",
                "source": "YouTube Data API v3",
            })
    return out


def channel_details(ids):
    out = []
    for i in range(0, len(ids), 50):
        data = _get("channels", {"part": "snippet,statistics", "id": ",".join(ids[i:i + 50])})
        for c in data.get("items", []):
            st, sn = c.get("statistics", {}), c.get("snippet", {})
            hidden = st.get("hiddenSubscriberCount")
            out.append({
                "platform": "YouTube",
                "id": c["id"],
                "name": sn.get("title"),
                "url": f"https://www.youtube.com/channel/{c['id']}",
                "handle": sn.get("customUrl"),
                "followers": None if hidden else int(st.get("subscriberCount", 0)),
                "followers_note": "hidden by channel" if hidden else "YouTube rounds subscriber counts to 3 significant figures",
                "total_views": int(st.get("viewCount", 0)),
                "video_count": int(st.get("videoCount", 0)),
                "country": sn.get("country"),
            })
    return out


def test():
    data = _get("videos", {"part": "id", "chart": "mostPopular", "maxResults": 1})
    return f"Connected. API key valid ({len(data.get('items', []))} test result)."
