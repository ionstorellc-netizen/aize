"""Central paths and environment settings."""
import os
from pathlib import Path

ROOT = Path(os.environ.get("STUDIO_ROOT", Path(__file__).resolve().parents[2]))
try:  # optional .env at the project root
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except ImportError:
    pass
STORAGE = Path(os.environ.get("STUDIO_STORAGE", ROOT / "storage"))
ASSETS = ROOT / "assets"
FONTS_DIR = ASSETS / "fonts"
SFX_DIR = STORAGE / "sfx"
MUSIC_DIR = STORAGE / "music"
PROJECTS_DIR = STORAGE / "projects"
LIBRARY_DIR = STORAGE / "library"
REFERENCES_DIR = STORAGE / "references"
MODELS_DIR = STORAGE / "models"
FRONTEND_DIST = ROOT / "frontend" / "dist"
DEFAULTS_DIR = Path(__file__).resolve().parent / "defaults"

DATABASE_URL = os.environ.get("DATABASE_URL", f"sqlite:///{STORAGE / 'studio.db'}")

# faster-whisper model: a local CTranslate2 folder or a model name ("small", "medium", "large-v3")
WHISPER_MODEL = os.environ.get("WHISPER_MODEL", "")
WHISPER_DEVICE = os.environ.get("WHISPER_DEVICE", "cpu")
WHISPER_COMPUTE = os.environ.get("WHISPER_COMPUTE", "int8")

WORKER_THREADS = int(os.environ.get("WORKER_THREADS", "2"))
FFMPEG = os.environ.get("FFMPEG_BIN", "ffmpeg")
FFPROBE = os.environ.get("FFPROBE_BIN", "ffprobe")

for d in (STORAGE, SFX_DIR, MUSIC_DIR, PROJECTS_DIR, LIBRARY_DIR, REFERENCES_DIR, MODELS_DIR):
    d.mkdir(parents=True, exist_ok=True)


def whisper_model_path() -> str:
    if WHISPER_MODEL:
        return WHISPER_MODEL
    local = MODELS_DIR / "whisper-small"
    if (local / "model.bin").exists():
        return str(local)
    return "small"  # downloaded automatically by faster-whisper on first use
