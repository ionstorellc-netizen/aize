import json
import re
import subprocess
from pathlib import Path

from .config import FFMPEG, FFPROBE


class StageError(Exception):
    """A user-facing error raised by a pipeline stage."""


def run(cmd, timeout=3600):
    p = subprocess.run([str(c) for c in cmd], capture_output=True, text=True, timeout=timeout)
    if p.returncode != 0:
        tail = "\n".join(p.stderr.strip().splitlines()[-15:])
        raise StageError(f"{Path(str(cmd[0])).name} failed: {tail}")
    return p


def ffmpeg(*args, timeout=3600):
    return run([FFMPEG, "-hide_banner", "-loglevel", "error", "-y", *args], timeout=timeout)


def probe(path):
    p = run([FFPROBE, "-v", "error", "-print_format", "json", "-show_format", "-show_streams", path])
    info = json.loads(p.stdout)
    out = {"duration": float(info.get("format", {}).get("duration", 0) or 0), "video": None, "audio": None}
    for st in info.get("streams", []):
        if st.get("codec_type") == "video" and out["video"] is None:
            num, den = (st.get("r_frame_rate") or "0/1").split("/")
            rot = 0
            for sd in st.get("side_data_list", []) or []:
                if "rotation" in sd:
                    rot = int(sd["rotation"])
            out["video"] = {"codec": st.get("codec_name"), "width": st.get("width"), "height": st.get("height"),
                            "fps": round(float(num) / float(den or 1), 3), "pix_fmt": st.get("pix_fmt"),
                            "rotation": rot}
        if st.get("codec_type") == "audio" and out["audio"] is None:
            out["audio"] = {"codec": st.get("codec_name"), "sample_rate": int(st.get("sample_rate", 0)),
                            "channels": st.get("channels")}
    return out


def loudness(path):
    p = run([FFMPEG, "-hide_banner", "-nostats", "-i", path, "-vn", "-af", "ebur128=peak=true", "-f", "null", "-"])
    txt = p.stderr
    def grab(label):
        m = re.findall(label + r":\s+(-?[\d.]+|-inf)", txt)
        return float(m[-1]) if m and m[-1] != "-inf" else None
    return {"integrated_lufs": grab("I"), "true_peak_db": grab("Peak"), "lra": grab("LRA")}


def hex_to_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def ass_color(h, alpha=0):
    r, g, b = hex_to_rgb(h)
    return f"&H{alpha:02X}{b:02X}{g:02X}{r:02X}"


def write_json(path, obj):
    Path(path).write_text(json.dumps(obj, ensure_ascii=False, indent=2))


ARABIC = re.compile(r"[؀-ۿݐ-ݿﭐ-﷿ﹰ-﻿]")
DEVANAGARI = re.compile(r"[ऀ-ॿ]")


def has_non_roman(text):
    return bool(ARABIC.search(text) or DEVANAGARI.search(text))
