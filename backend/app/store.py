"""Persistent settings and encrypted server-side secrets."""
import json
import os
import stat
from copy import deepcopy

from cryptography.fernet import Fernet, InvalidToken

from .config import STORAGE, DEFAULTS_DIR
from .db import SessionLocal, Setting, IntegrationEvent

# ---------------------------------------------------------------- settings

DEFAULT_PREFERENCES = {
    "default_duration_s": [30, 50],
    "categories": ["Amazon", "Shopify", "China Sourcing", "AI Automation", "Product Hunting",
                   "E-commerce News", "Business Case Studies", "Tutorials"],
    "markets": ["SA", "AE", "US", "GB", "CA", "AU", "JP"],
    "language": "roman_urdu",
    "claude_model": "claude-opus-5-5",
    "claude_effort": "medium",
    "export": {"width": 1080, "height": 1920, "fps": 30, "vcodec": "libx264", "crf": 18,
               "preset": "medium", "acodec": "aac", "abitrate": "192k"},
    "broll": {"prefer": ["library", "pexels", "generated"], "allow_generated_graphics": True,
              "avoid_repeat": True},
    "audio": {"music": "generated_pad", "music_asset_id": None},
    "require_final_approval": True,
    "whisper_prompt": "Toh dosto, aaj hum baat karenge Amazon FBA, private label, product hunting aur China sourcing ke baare mein. Agar aap business start karna chahte hain to yeh video zaroor dekhein.",
}


def _load_default(name):
    return json.loads((DEFAULTS_DIR / f"{name}.json").read_text())


DEFAULTS = {
    "style_profile": lambda: _load_default("style_profile"),
    "avatar_profile": lambda: _load_default("avatar_profile"),
    "preferences": lambda: deepcopy(DEFAULT_PREFERENCES),
}


def get_setting(key):
    with SessionLocal() as s:
        row = s.get(Setting, key)
        if row is None:
            val = DEFAULTS[key]() if key in DEFAULTS else {}
            s.add(Setting(key=key, value=val))
            s.commit()
            return deepcopy(val)
        val = deepcopy(row.value)
        if key == "preferences":  # forward-fill new default keys
            for k, v in DEFAULT_PREFERENCES.items():
                val.setdefault(k, deepcopy(v))
        return val


def set_setting(key, value):
    with SessionLocal() as s:
        row = s.get(Setting, key)
        if row is None:
            s.add(Setting(key=key, value=value))
        else:
            row.value = value
        s.commit()


def reset_setting(key):
    set_setting(key, DEFAULTS[key]())


# ---------------------------------------------------------------- secrets

SECRET_FIELDS = {
    "anthropic": [("ANTHROPIC_API_KEY", True)],
    "youtube": [("YOUTUBE_API_KEY", True)],
    "pexels": [("PEXELS_API_KEY", True)],
    "pixabay": [("PIXABAY_API_KEY", True)],
    "heygen": [("HEYGEN_API_KEY", True), ("HEYGEN_AVATAR_ID", False), ("HEYGEN_VOICE_ID", False)],
    "instagram": [("INSTAGRAM_ACCESS_TOKEN", True), ("INSTAGRAM_BUSINESS_ID", False)],
}
_KEYFILE = STORAGE / ".secret_key"
_SECRETS = STORAGE / "secrets.enc"


def _fernet():
    key = os.environ.get("APP_SECRET_KEY")
    if not key:
        if not _KEYFILE.exists():
            _KEYFILE.write_bytes(Fernet.generate_key())
            os.chmod(_KEYFILE, stat.S_IRUSR | stat.S_IWUSR)
        key = _KEYFILE.read_bytes().decode()
    return Fernet(key.encode() if isinstance(key, str) else key)


def _read_all():
    if not _SECRETS.exists():
        return {}
    try:
        return json.loads(_fernet().decrypt(_SECRETS.read_bytes()))
    except (InvalidToken, ValueError):
        return {}


def save_secret(name, value):
    data = _read_all()
    if value:
        data[name] = value
    else:
        data.pop(name, None)
    _SECRETS.write_bytes(_fernet().encrypt(json.dumps(data).encode()))
    os.chmod(_SECRETS, stat.S_IRUSR | stat.S_IWUSR)


def get_secret(name):
    """Environment variables win over values saved from the UI."""
    return os.environ.get(name) or _read_all().get(name) or ""


def secret_status(name):
    if os.environ.get(name):
        return "env"
    return "saved" if _read_all().get(name) else "missing"


def masked(name):
    v = get_secret(name)
    if not v:
        return ""
    return v if len(v) < 12 and not name.endswith(("KEY", "TOKEN")) else "•••• " + v[-4:]


# ---------------------------------------------------------------- integration log

def log_event(provider, kind, ok, message, units=0.0, cost=0.0, project_id=None):
    with SessionLocal() as s:
        s.add(IntegrationEvent(provider=provider, kind=kind, ok=1 if ok else 0, message=str(message)[:4000],
                               units=units, cost_usd=cost, project_id=project_id))
        s.commit()
