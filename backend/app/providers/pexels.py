"""Pexels video API: licensed stock B-roll (Pexels License, free to use, no attribution required)."""
from pathlib import Path

import httpx

from ..store import get_secret, log_event
from ..util import StageError

BASE = "https://api.pexels.com"


def configured():
    return bool(get_secret("PEXELS_API_KEY"))


def _headers():
    key = get_secret("PEXELS_API_KEY")
    if not key:
        raise StageError("Pexels is not configured. Add PEXELS_API_KEY in Integrations.")
    return {"Authorization": key}


def search(query, per_page=8, orientation="portrait"):
    try:
        r = httpx.get(f"{BASE}/videos/search", headers=_headers(),
                      params={"query": query, "per_page": per_page, "orientation": orientation, "size": "medium"},
                      timeout=30)
    except httpx.HTTPError as e:
        log_event("pexels", "error", False, f"search '{query}': {e}")
        raise StageError(f"Could not reach Pexels: {e}") from e
    if r.status_code != 200:
        log_event("pexels", "error", False, f"search '{query}': {r.status_code} {r.text[:200]}")
        raise StageError(f"Pexels error {r.status_code}")
    log_event("pexels", "call", True, f"search '{query}'", units=1)
    out = []
    for v in r.json().get("videos", []):
        files = [f for f in v.get("video_files", []) if f.get("file_type") == "video/mp4" and f.get("height")]
        if not files:
            continue
        # prefer ~1080p portrait-ish file, cap bandwidth
        files.sort(key=lambda f: abs((f.get("height") or 0) - 1920))
        f = files[0]
        out.append({"provider": "pexels", "id": str(v["id"]), "url": v.get("url"), "download": f["link"],
                    "width": f.get("width"), "height": f.get("height"), "duration": v.get("duration"),
                    "author": (v.get("user") or {}).get("name"), "query": query,
                    "license": "Pexels License (free commercial use)"})
    return out


def download(item, dest: Path):
    dest.parent.mkdir(parents=True, exist_ok=True)
    with httpx.stream("GET", item["download"], follow_redirects=True, timeout=120) as r:
        r.raise_for_status()
        with open(dest, "wb") as fh:
            for chunk in r.iter_bytes(1 << 16):
                fh.write(chunk)
    return dest


def test():
    r = httpx.get(f"{BASE}/videos/search", headers=_headers(), params={"query": "warehouse", "per_page": 1}, timeout=20)
    if r.status_code != 200:
        raise StageError(f"Pexels returned {r.status_code}: {r.text[:200]}")
    return f"Connected. Rate limit remaining: {r.headers.get('X-Ratelimit-Remaining', 'n/a')}"
