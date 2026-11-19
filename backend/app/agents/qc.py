"""Quality Control Agent: measurable checks on the rendered master + optional Claude vision review."""
import re
from pathlib import Path

from ..config import FFMPEG
from ..providers import claude
from ..util import probe, loudness, run, has_non_roman, ffmpeg
from ..engine.edl import resolved
from .schemas import VisionQC


def _check(name, status, detail, critical=False):
    return {"check": name, "status": status, "detail": detail, "critical": critical}


def run_qc(master: Path, edl, style, prefs, reference_frame: Path | None, avatar_mode: str, workdir: Path,
           project_id=None):
    exp = prefs["export"]
    lo, hi = prefs["default_duration_s"]
    checks = []
    info = probe(master)
    v, a = info["video"] or {}, info["audio"] or {}
    dur = info["duration"]
    checks.append(_check("Video duration", "pass" if lo <= dur <= hi else "fail",
                         f"{dur:.1f}s (target {lo}-{hi}s)", critical=True))
    ok_res = v.get("width") == exp["width"] and v.get("height") == exp["height"]
    checks.append(_check("Aspect ratio / resolution", "pass" if ok_res else "fail",
                         f"{v.get('width')}x{v.get('height')} (9:16 {exp['width']}x{exp['height']} required)", critical=True))
    checks.append(_check("Frame rate", "pass" if abs((v.get("fps") or 0) - exp["fps"]) < 0.5 else "fail",
                         f"{v.get('fps')} fps", critical=True))
    checks.append(_check("Export integrity (codecs)",
                         "pass" if v.get("codec") == "h264" and a.get("codec") == "aac" else "fail",
                         f"video {v.get('codec')}, audio {a.get('codec')}", critical=True))
    # full decode = integrity
    p = run([FFMPEG, "-v", "error", "-i", str(master), "-f", "null", "-"])
    checks.append(_check("Decode test", "pass" if not p.stderr.strip() else "fail",
                         "decodes cleanly" if not p.stderr.strip() else p.stderr[:300], critical=True))
    # audio
    ld = loudness(master)
    tp, li = ld["true_peak_db"], ld["integrated_lufs"]
    checks.append(_check("Audio clipping", "pass" if tp is not None and tp <= -0.5 else "fail",
                         f"true peak {tp} dBTP", critical=True))
    checks.append(_check("Audio loudness", "pass" if li is not None and -18 <= li <= -12 else "warn",
                         f"{li} LUFS integrated (target about -14 to -16 for social)"))
    # black / frozen
    p = run([FFMPEG, "-hide_banner", "-i", str(master), "-vf", "blackdetect=d=0.4:pix_th=0.08", "-an", "-f", "null", "-"])
    blacks = [(float(s), float(e)) for s, e in re.findall(r"black_start:([\d.]+) black_end:([\d.]+)", p.stderr)]
    blacks = [b for b in blacks if b[0] < dur - 1.6]  # ignore the intended end fade
    checks.append(_check("Black frames", "pass" if not blacks else "fail",
                         "none" if not blacks else f"{len(blacks)} black section(s) at {[round(b[0],1) for b in blacks]}", critical=True))
    p = run([FFMPEG, "-hide_banner", "-i", str(master), "-vf", "freezedetect=n=0.002:d=2.5", "-an", "-f", "null", "-"])
    freezes = re.findall(r"freeze_start: ([\d.]+)", p.stderr)
    checks.append(_check("Frozen video", "pass" if not freezes else "warn",
                         "none" if not freezes else f"static sections at {freezes} s (check graphics/B-roll)"))
    # subtitles
    res = resolved(edl)
    subs = res["subtitles"]
    non_roman = [w["w"] for ph in subs for w in ph["words"] if has_non_roman(w["w"])]
    checks.append(_check("Roman Urdu script", "pass" if not non_roman else "fail",
                         "all subtitle text is Latin script" if not non_roman else f"non-Roman words: {non_roman[:8]}", critical=True))
    bad_t = [ph for ph in subs if ph["t1"] - ph["t0"] < 0.2 or ph["t1"] > dur + 0.05]
    overl = sum(1 for x, y in zip(subs, subs[1:]) if y["t0"] < x["t1"] - 0.01)
    checks.append(_check("Subtitle timing", "pass" if not bad_t and not overl else "warn",
                         f"{len(subs)} captions, {len(bad_t)} too short/out of range, {overl} overlaps"))
    low_conf = edl.get("_low_confidence_words", [])
    checks.append(_check("Roman Urdu spelling", "warn" if low_conf else "pass",
                         f"{len(low_conf)} low-confidence words to review: {low_conf[:10]}" if low_conf else
                         "recogniser confidence OK" + (" (Claude-polished)" if edl.get("_subtitles_polished") else "")))
    # b-roll
    cover = sum(b["dur"] for b in res["broll"]) / max(dur, 1)
    target = style["broll"]["coverage_target"]
    checks.append(_check("B-roll coverage", "pass" if cover >= target * 0.6 else "warn",
                         f"{cover * 100:.0f}% of runtime (style target {target * 100:.0f}%)"))
    srcs = {}
    for b in res["broll"]:
        srcs[b.get("source", "?")] = srcs.get(b.get("source", "?"), 0) + 1
    checks.append(_check("B-roll relevance", "info",
                         f"sources: {srcs}. Each pick is tied to the sentence it covers; review in the timeline."))
    rep = len(res["broll"]) - len({b["path"] for b in res["broll"]})
    checks.append(_check("B-roll repetition", "pass" if rep == 0 else "warn", f"{rep} repeated clips"))
    sfx_db = edl["audio"].get("sfx_db", -22)
    checks.append(_check("Sound effect volume", "pass" if -30 <= sfx_db <= -18 else "warn", f"SFX at {sfx_db} dB, music at {edl['audio'].get('music_db')} dB, ducked under voice"))
    checks.append(_check("Watermarks (engine)", "pass", "the engine adds no watermark or third-party branding"))
    # lip sync
    if avatar_mode == "own_recording":
        checks.append(_check("Lip synchronisation", "pass", "original camera recording; picture and voice come from the same take and every cut is applied to both"))
    else:
        checks.append(_check("Lip synchronisation", "manual", "AI avatar output: watch the preview to confirm lip sync"))
    # vision (Claude)
    if claude.configured() and reference_frame and Path(reference_frame).exists():
        frames = []
        for i, t in enumerate([dur * 0.15, dur * 0.45, dur * 0.75]):
            f = workdir / f"qc_{i}.jpg"
            ffmpeg("-ss", f"{t:.2f}", "-i", str(master), "-frames:v", "1", "-vf", "scale=540:-2", str(f))
            frames.append(f)
        content = [{"type": "text", "text": "Image 1 is the presenter's identity reference. Images 2-4 are frames from the finished video."},
                   claude.image_block(reference_frame)] + [claude.image_block(f) for f in frames] + [
                  {"type": "text", "text": "Is the main presenter in images 2-4 the same person as image 1 (ignore B-roll/graphics frames)? "
                                           "Is any third-party watermark/logo/creator handle visible? Is visual quality acceptable (sharp, well exposed, nothing broken)?"}]
        vq = claude.structured("You are a strict video quality-control reviewer.", content, VisionQC,
                               project_id=project_id, purpose="qc_vision", effort="low")
        checks.append(_check("Avatar identity consistency", "pass" if vq.same_person_as_reference else "fail",
                             vq.identity_notes, critical=True))
        checks.append(_check("Watermarks (visual)", "fail" if vq.visible_third_party_watermark else "pass", vq.watermark_notes, critical=True))
        checks.append(_check("Visual quality", "pass" if vq.visual_quality_ok else "warn", vq.visual_notes))
    else:
        checks.append(_check("Avatar identity consistency", "manual",
                             "own recording of the configured presenter" if avatar_mode == "own_recording"
                             else "configure Claude for an automatic vision check, or confirm manually"))
        checks.append(_check("Visual quality", "manual", "review the preview"))
    critical_fail = [c for c in checks if c["critical"] and c["status"] == "fail"]
    return {"passed": not critical_fail, "critical_failures": [c["check"] for c in critical_fail], "checks": checks,
            "duration": dur, "loudness": ld}
