"""HeyGen avatar video generation (Digital Twin + cloned voice).

Docs: https://docs.heygen.com  — v2/video/generate, v1/video_status.get
Status in this build: implemented against HeyGen's published API; awaiting your key for a live test.
"""
import time
from pathlib import Path

import httpx

from ..store import get_secret, log_event
from ..util import StageError

BASE = "https://api.heygen.com"


def configured():
    return bool(get_secret("HEYGEN_API_KEY") and get_secret("HEYGEN_AVATAR_ID") and get_secret("HEYGEN_VOICE_ID"))


def _h():
    key = get_secret("HEYGEN_API_KEY")
    if not key:
        raise StageError("HeyGen is not configured. Add HEYGEN_API_KEY in Integrations.")
    return {"X-Api-Key": key, "Content-Type": "application/json", "Accept": "application/json"}


def _check(r, what, project_id=None):
    try:
        body = r.json()
    except ValueError:
        body = {"raw": r.text[:300]}
    if r.status_code >= 400 or body.get("error"):
        msg = body.get("error") or body.get("message") or body
        log_event("heygen", "error", False, f"{what}: {r.status_code} {msg}", project_id=project_id)
        raise StageError(f"HeyGen {what} failed ({r.status_code}): {msg}")
    return body


def generate(text, project_id=None, width=1080, height=1920, speed=1.0):
    avatar_id, voice_id = get_secret("HEYGEN_AVATAR_ID"), get_secret("HEYGEN_VOICE_ID")
    if not (avatar_id and voice_id):
        raise StageError("Set your HeyGen avatar_id and voice_id in Integrations (your own Digital Twin only).")
    payload = {
        "video_inputs": [{
            "character": {"type": "avatar", "avatar_id": avatar_id, "avatar_style": "normal"},
            "voice": {"type": "text", "input_text": text, "voice_id": voice_id, "speed": speed},
        }],
        "dimension": {"width": width, "height": height},
        "caption": False,
    }
    r = httpx.post(f"{BASE}/v2/video/generate", headers=_h(), json=payload, timeout=60)
    body = _check(r, "generate", project_id)
    vid = (body.get("data") or {}).get("video_id")
    if not vid:
        raise StageError(f"HeyGen did not return a video_id: {body}")
    log_event("heygen", "call", True, f"generate video {vid} ({len(text.split())} words)", units=1, project_id=project_id)
    return vid


def wait(video_id, dest: Path, timeout_s=1800, project_id=None, on_status=None):
    t0 = time.time()
    while time.time() - t0 < timeout_s:
        r = httpx.get(f"{BASE}/v1/video_status.get", headers=_h(), params={"video_id": video_id}, timeout=30)
        data = _check(r, "status", project_id).get("data") or {}
        st = data.get("status")
        if on_status:
            on_status(st)
        if st == "completed":
            with httpx.stream("GET", data["video_url"], follow_redirects=True, timeout=300) as dl:
                dl.raise_for_status()
                with open(dest, "wb") as fh:
                    for chunk in dl.iter_bytes(1 << 16):
                        fh.write(chunk)
            return dest
        if st == "failed":
            raise StageError(f"HeyGen render failed: {data.get('error')}")
        time.sleep(10)
    raise StageError("HeyGen render timed out. Retry this stage to keep polling the same job.")


def test():
    r = httpx.get(f"{BASE}/v2/user/remaining_quota", headers=_h(), timeout=20)
    body = _check(r, "quota")
    quota = (body.get("data") or {}).get("remaining_quota")
    msg = f"Connected. Remaining quota: {quota}."
    aid = get_secret("HEYGEN_AVATAR_ID")
    if aid:
        r2 = httpx.get(f"{BASE}/v2/avatars", headers=_h(), timeout=30)
        avatars = (_check(r2, "avatars").get("data") or {}).get("avatars", [])
        found = any(a.get("avatar_id") == aid for a in avatars)
        msg += " Avatar ID found." if found else " Warning: avatar_id not found in your HeyGen account."
    return msg
