"""Pixabay video API: free stock B-roll (Pixabay Content License, free commercial use, no attribution required).

Free key, issued instantly at https://pixabay.com/api/docs/ (sign in, the key is shown on that page).
Pixabay does not allow hotlinking, so clips are always downloaded before use.
"""
from pathlib import Path
from urllib.parse import urlparse

import httpx

from ..store import get_secret, log_event
from ..util import StageError

BASE = "https://pixabay.com/api/videos/"
LICENSE = "Pixabay Content License (free commercial use)"


def configured():
    return bool(get_secret("PIXABAY_API_KEY"))


def _key():
    key = get_secret("PIXABAY_API_KEY")
    if not key:
        raise StageError("Pixabay is not configured. Add PIXABAY_API_KEY in Integrations.")
    return key


def _get(params, timeout=30):
    return httpx.get(BASE, params={"key": _key(), "safesearch": "true", **params}, timeout=timeout)


def _pick_file(videos):
    """Smallest rendition that is still at least 720p on its short side (else the biggest one there is)."""
    files = [f for f in (videos or {}).values() if isinstance(f, dict) and f.get("url") and f.get("width") and f.get("height")]
    if not files:
        return None
    good = [f for f in files if min(f["width"], f["height"]) >= 720]
    if good:
        return min(good, key=lambda f: f["width"] * f["height"])
    return max(files, key=lambda f: f["width"] * f["height"])


def _error(r):
    msg = r.text.strip()[:200]
    if r.status_code in (400, 401, 403) and "key" in msg.lower():
        return "Pixabay rejected the API key. Copy it again from pixabay.com/api/docs."
    if r.status_code == 429:
        return "Pixabay rate limit reached (100 requests per minute). Try again in a minute."
    return f"Pixabay error {r.status_code}: {msg}"


def search(query, per_page=8, **_):
    try:
        r = _get({"q": query[:100], "per_page": max(3, min(per_page, 200))})
    except httpx.HTTPError as e:
        log_event("pixabay", "error", False, f"search '{query}': {type(e).__name__}")
        raise StageError(f"Could not reach Pixabay ({type(e).__name__}).") from None
    if r.status_code != 200:
        log_event("pixabay", "error", False, f"search '{query}': {r.status_code} {r.text[:200]}")
        raise StageError(_error(r))
    log_event("pixabay", "call", True, f"search '{query}'", units=1)
    out = []
    for v in r.json().get("hits", []):
        f = _pick_file(v.get("videos"))
        if not f:
            continue
        out.append({"provider": "pixabay", "id": str(v["id"]), "url": v.get("pageURL"), "download": f["url"],
                    "width": f["width"], "height": f["height"], "duration": v.get("duration"),
                    "author": v.get("user"), "query": query, "license": LICENSE})
    # portrait clips first (they fill a 9:16 frame without cropping); otherwise keep Pixabay's relevance order
    out.sort(key=lambda x: 0 if x["height"] >= x["width"] else 1)
    return out


def download(item, dest: Path):
    if not (urlparse(item.get("download", "")).hostname or "").endswith("pixabay.com"):
        raise StageError("Not a Pixabay download link.")
    dest.parent.mkdir(parents=True, exist_ok=True)
    with httpx.stream("GET", item["download"], follow_redirects=True, timeout=120) as r:
        r.raise_for_status()
        with open(dest, "wb") as fh:
            for chunk in r.iter_bytes(1 << 16):
                fh.write(chunk)
    return dest


def test():
    try:
        r = _get({"q": "warehouse", "per_page": 3}, timeout=20)
    except httpx.HTTPError as e:
        raise StageError(f"Could not reach Pixabay ({type(e).__name__}).") from None
    if r.status_code != 200:
        raise StageError(_error(r))
    total = r.json().get("totalHits", 0)
    return f"Connected. {total} videos found for 'warehouse'. Rate limit remaining: {r.headers.get('X-RateLimit-Remaining', 'n/a')}"
