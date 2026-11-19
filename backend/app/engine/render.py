"""EDL -> MP4 renderer (FFmpeg + libass + Pillow overlays)."""
import json
import re
import shutil
from pathlib import Path

from ..config import FONTS_DIR, FFMPEG
from ..util import ffmpeg, run, probe, ass_color, StageError
from . import graphics, sfx
from .edl import resolved
import os
from ..config import STORAGE


def _setup_fontconfig():
    """Make libass see the bundled fonts (fontsdir alone is ignored when fontconfig is the provider)."""
    conf = STORAGE / "fontconfig.conf"
    conf.write_text(
        '<?xml version="1.0"?><!DOCTYPE fontconfig SYSTEM "fonts.dtd"><fontconfig>'
        '<include ignore_missing="yes">/etc/fonts/fonts.conf</include>'
        f'<dir>{FONTS_DIR}</dir><cachedir>{STORAGE / "fontcache"}</cachedir></fontconfig>')
    os.environ["FONTCONFIG_FILE"] = str(conf)


_setup_fontconfig()


def normalize_source(src, out, W=1080, H=1920, fps=30):
    """Any phone/HeyGen clip -> 9:16 1080x1920, constant 30 fps, H.264 + 48 kHz AAC (edit-friendly)."""
    vf = f"scale={W}:{H}:force_original_aspect_ratio=increase:flags=lanczos,crop={W}:{H},fps={fps},format=yuv420p"
    ffmpeg("-i", str(src), "-vf", vf, "-c:v", "libx264", "-preset", "fast", "-crf", "16", "-g", "30",
           "-c:a", "aac", "-b:a", "256k", "-ar", "48000", "-ac", "2", "-movflags", "+faststart", str(out))
    return out


# ------------------------------------------------------------------ subtitles (ASS)

def _ts(t):
    t = max(0, t)
    h, m = int(t // 3600), int(t % 3600 // 60)
    s = t % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def write_ass(res, style, path, W=1080, H=1920):
    sub, pal = style["subtitles"], style["palette"]
    margin_v = int(H * (1 - sub["position_y_ratio"]))
    font_name = "Playfair Display"
    head = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Cap,{font_name},{sub['font_size']},{ass_color(sub['text_color'])},{ass_color(sub['text_color'])},{ass_color(sub['box_color'], 0x10)},{ass_color(sub['box_color'], 0x10)},0,0,0,0,100,100,0,0,{3 if sub.get('box', True) else 1},14,0,2,60,60,{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    cream, gold, muted = ass_color(sub["text_color"]), ass_color(sub["active_word_color"]), ass_color(sub["upcoming_word_color"])
    lines = []
    for ph in res["subtitles"]:
        ws = ph["words"]
        for k, w in enumerate(ws):
            t0 = w["t0"] if k else ph["t0"]
            t1 = ws[k + 1]["t0"] if k + 1 < len(ws) else ph["t1"]
            if t1 - t0 < 0.02:
                continue
            parts = []
            for j, x in enumerate(ws):
                col = cream if j < k else gold if j == k else muted
                txt = x["w"].replace("{", "(").replace("}", ")")
                if sub.get("uppercase"):
                    txt = txt.upper()
                parts.append(f"{{\\c{col}}}{txt}")
            anim = "{\\fscx92\\fscy92\\t(0,90,\\fscx100\\fscy100)}" if k == 0 else ""
            lines.append(f"Dialogue: 0,{_ts(t0)},{_ts(t1)},Cap,,0,0,0,,{anim}{' '.join(parts)}")
    Path(path).write_text(head + "\n".join(lines) + "\n", encoding="utf-8")
    return path


def write_srt(res, path):
    out = []
    def ts(t):
        ms = int(round(t * 1000))
        return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"
    for i, ph in enumerate(res["subtitles"], 1):
        out.append(f"{i}\n{ts(ph['t0'])} --> {ts(ph['t1'])}\n{' '.join(w['w'] for w in ph['words'])}\n")
    Path(path).write_text("\n".join(out), encoding="utf-8")
    return path


# ------------------------------------------------------------------ helpers

def _grade_filter(g):
    w = g.get("warmth", 0)
    f = (f"eq=contrast={g.get('contrast', 1)}:saturation={g.get('saturation', 1)}:brightness={g.get('brightness', 0)}"
         f":gamma={g.get('gamma', 1)},colorbalance=rs={w:.3f}:gs={w / 3:.3f}:bs={-w:.3f}:rm={w / 2:.3f}:bm={-w / 2:.3f}")
    if g.get("vignette", 0) > 0:
        f += f",vignette=angle={0.2 + 0.6 * g['vignette']:.3f}"
    return f


def _loudnorm_params(path, I, TP):
    p = run([FFMPEG, "-hide_banner", "-nostats", "-i", str(path), "-vn", "-af",
             f"loudnorm=I={I}:TP={TP}:LRA=11:print_format=json", "-f", "null", "-"])
    m = re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", p.stderr, re.S)
    if not m:
        return f"loudnorm=I={I}:TP={TP}:LRA=11"
    d = json.loads(m.group(0))
    if d["input_i"] in ("-inf", "inf"):
        return f"loudnorm=I={I}:TP={TP}:LRA=11"
    return (f"loudnorm=I={I}:TP={TP}:LRA=11:measured_I={d['input_i']}:measured_TP={d['input_tp']}:"
            f"measured_LRA={d['input_lra']}:measured_thresh={d['input_thresh']}:offset={d['target_offset']}:linear=true")


# ------------------------------------------------------------------ render

def render(edl, style, workdir: Path, out_path: Path, preview=False, music_path=None, log=print, crf=18, preset="medium"):
    workdir = Path(workdir)
    tmp = workdir / ("render_preview" if preview else "render_final")
    if tmp.exists():
        shutil.rmtree(tmp)
    tmp.mkdir(parents=True)
    W, H, fps = edl["canvas"]["width"], edl["canvas"]["height"], edl["canvas"]["fps"]
    res = resolved(edl)
    total = res["duration"]
    if total <= 0 or not edl["segments"]:
        raise StageError("The edit has no shots. Add at least one scene in the timeline.")
    src = edl["source"]
    xenc = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "15", "-pix_fmt", "yuv420p", "-g", str(fps)]

    # ---- A: cut + reframe each shot
    log(f"Cutting {len(edl['segments'])} shots")
    listfile = tmp / "concat.txt"
    with open(listfile, "w") as lf:
        for i, s in enumerate(edl["segments"]):
            z = max(1.0, float(s.get("zoom", 1.0)))
            cw, ch = int(W / z) // 2 * 2, int(H / z) // 2 * 2
            x, y = (W - cw) // 2, int((H - ch) * 0.35)
            d = s["src_out"] - s["src_in"]
            vf = f"crop={cw}:{ch}:{x}:{y},scale={W}:{H}:flags=lanczos,setsar=1,fps={fps}"
            af = f"afade=t=in:d=0.012,afade=t=out:st={max(0, d - 0.015):.3f}:d=0.015"
            seg = tmp / f"seg_{i:03d}.mp4"
            ffmpeg("-ss", f"{s['src_in']:.3f}", "-i", src, "-t", f"{d:.3f}", "-vf", vf, "-af", af, *xenc,
                   "-c:a", "pcm_s16le", "-ar", "48000", "-ac", "2", str(seg.with_suffix(".mov")))
            lf.write(f"file '{seg.with_suffix('.mov').name}'\n")
    base = tmp / "base.mov"
    ffmpeg("-f", "concat", "-safe", "0", "-i", str(listfile), "-c", "copy", str(base))
    total = probe(base)["duration"] or total

    # ---- B: overlay assets
    sfx_paths = sfx.ensure_assets()
    inputs, fc, n = ["-i", str(base)], [], 1
    fc.append(f"[0:v]{_grade_filter(edl.get('grade', {}))},format=yuv420p[v0]")
    cur = "v0"
    card = style["broll"]["card"]
    cwid = int(W * card["width_ratio"]) // 2 * 2
    chei = int(cwid * 0.75) // 2 * 2
    mask = graphics.card_mask(cwid, chei, card["corner_radius"], tmp / "card_mask.png")
    frame, pad = graphics.card_frame(cwid, chei, card["corner_radius"], card["border_px"], card["border_color"], tmp / "card_frame.png")
    for i, b in enumerate(res["broll"]):
        t, d = b["t"], b["dur"]
        if t >= total - 0.1:
            continue
        d = min(d, total - t)
        if b.get("media") == "image":
            inputs += ["-loop", "1", "-t", f"{d + 0.1:.3f}", "-i", b["path"]]
            trim = f"trim=duration={d:.3f},setpts=PTS-STARTPTS"
        else:
            inputs += ["-stream_loop", "-1", "-i", b["path"]]
            trim = f"trim=start={b.get('in', 0):.3f}:duration={d:.3f},setpts=PTS-STARTPTS"
        vin = n
        n += 1
        fade = f"fade=t=in:st=0:d=0.12:alpha=1,fade=t=out:st={max(0, d - 0.12):.3f}:d=0.12:alpha=1"
        if b.get("mode") == "full":
            fc.append(f"[{vin}:v]{trim},fps={fps},scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
                      f"setsar=1,{_grade_filter(edl.get('grade', {}))},format=yuva420p,{fade},setpts=PTS+{t:.3f}/TB[b{i}]")
            fc.append(f"[{cur}][b{i}]overlay=0:0:eof_action=pass:enable='between(t,{t:.3f},{t + d:.3f})'[vb{i}]")
        else:
            inputs += ["-loop", "1", "-t", f"{d + 0.1:.3f}", "-i", str(mask)]
            min_ = n
            n += 1
            inputs += ["-loop", "1", "-t", f"{d + 0.1:.3f}", "-i", str(frame)]
            fin = n
            n += 1
            fc.append(f"[{vin}:v]{trim},fps={fps},scale={cwid}:{chei}:force_original_aspect_ratio=increase,"
                      f"crop={cwid}:{chei},setsar=1,format=yuva420p[bc{i}]")
            fc.append(f"[{min_}:v]format=gray,trim=duration={d:.3f},setpts=PTS-STARTPTS[bm{i}]")
            fc.append(f"[bc{i}][bm{i}]alphamerge[ba{i}]")
            fc.append(f"[{fin}:v]format=rgba,trim=duration={d:.3f},setpts=PTS-STARTPTS[bf{i}]")
            fc.append(f"[bf{i}][ba{i}]overlay={pad}:{pad}:format=auto,format=yuva420p,{fade},setpts=PTS+{t:.3f}/TB[b{i}]")
            x = (W - cwid) // 2 - pad
            y0 = int(H * card["y_ratio"]) - pad
            yexp = f"{y0}+50*max(0\\,1-(t-{t:.3f})/0.22)"
            fc.append(f"[{cur}][b{i}]overlay=x={x}:y='{yexp}':eof_action=pass:enable='between(t,{t:.3f},{t + d:.3f})'[vb{i}]")
        cur = f"vb{i}"

    # subtitles
    ass = write_ass(res, style, tmp / "subs.ass", W, H)
    fc.append(f"[{cur}]subtitles=filename='{ass}':fontsdir='{FONTS_DIR}'[vs]")
    cur = "vs"

    # titles
    tcfg = style["titles"]
    for i, ti in enumerate(res["titles"]):
        t, d = ti["t"], min(ti["dur"], max(0.2, total - ti["t"]))
        png = tmp / f"title_{i}.png"
        if ti["kind"] == "hook":
            graphics.hook_title(ti["text"], ti.get("sub", ""), style, png, W)
            y = int(H * 0.06)
        else:
            graphics.keyword_bar(ti["text"], ti.get("sub", ""), style, png, W)
            y = int(H * tcfg["position_y_ratio"])
        inputs += ["-loop", "1", "-t", f"{d + 0.1:.3f}", "-i", str(png)]
        fc.append(f"[{n}:v]format=yuva420p,trim=duration={d:.3f},fade=t=in:st=0:d=0.1:alpha=1,"
                  f"fade=t=out:st={max(0, d - 0.15):.3f}:d=0.15:alpha=1,setpts=PTS+{t:.3f}/TB[t{i}]")
        yexp = f"{y}+30*max(0\\,1-(t-{t:.3f})/0.18)"
        fc.append(f"[{cur}][t{i}]overlay=x=(W-w)/2:y='{yexp}':eof_action=pass:enable='between(t,{t:.3f},{t + d:.3f})'[vt{i}]")
        cur = f"vt{i}"
        n += 1

    # CTA
    cta = res.get("cta")
    if cta:
        t, d = cta["t"], total - cta["t"]
        png = graphics.cta_card(cta["text"], cta.get("sub", ""), style, tmp / "cta.png", W)
        inputs += ["-loop", "1", "-t", f"{d + 0.1:.3f}", "-i", str(png)]
        fc.append(f"[{n}:v]format=yuva420p,trim=duration={d:.3f},fade=t=in:st=0:d=0.2:alpha=1,setpts=PTS+{t:.3f}/TB[cta]")
        fc.append(f"[{cur}][cta]overlay=x=(W-w)/2:y={int(H * 0.07)}:eof_action=pass:enable='gte(t,{t:.3f})'[vc]")
        cur = "vc"
        n += 1
        fadeout = cta.get("fade", 1.0)
        fc.append(f"[{cur}]fade=t=out:st={max(0, total - fadeout):.3f}:d={fadeout:.3f}[vf]")
        cur = "vf"
    if preview:
        fc.append(f"[{cur}]scale={W // 2}:{H // 2}[vp]")
        cur = "vp"

    # ---- C: audio mix
    au = edl["audio"]
    ln = _loudnorm_params(base, au.get("voice_lufs", -15), au.get("voice_tp", -3))
    fc.append(f"[0:a]{ln},aresample=48000,asplit=2[voice][key]")
    mix = ["[voice]"]
    if au.get("music") == "library":
        mpath = au.get("music_path")
    elif au.get("music") == "generated_pad":
        mpath = music_path or sfx_paths.get("generated_pad")  # default music from Settings, else generated pad
    else:
        mpath = None
    if mpath and au.get("music") != "none":
        inputs += ["-stream_loop", "-1", "-i", str(mpath)]
        fc.append(f"[{n}:a]atrim=duration={total:.3f},aresample=48000,volume={au.get('music_db', -27)}dB,"
                  f"afade=t=in:d=0.8,afade=t=out:st={max(0, total - 1.5):.3f}:d=1.5[mus]")
        if au.get("duck", True):
            fc.append("[mus][key]sidechaincompress=threshold=0.03:ratio=6:attack=15:release=350:makeup=1[mduck]")
            mix.append("[mduck]")
        else:
            fc.append("[key]anullsink")
            mix.append("[mus]")
        n += 1
    else:
        fc.append("[key]anullsink")
    kinds = {}
    for e in res["sfx"]:
        if e["t"] < total - 0.05 and e["kind"] in sfx_paths:
            kinds.setdefault(e["kind"], []).append(e["t"])
    if cta:
        kinds.setdefault("notify", []).append(cta["t"] + 0.1)
    for kind, times in kinds.items():
        inputs += ["-i", str(sfx_paths[kind])]
        labels = [f"s_{kind}_{j}" for j in range(len(times))]
        fc.append(f"[{n}:a]aresample=48000,volume={au.get('sfx_db', -22)}dB,asplit={len(times)}" + "".join(f"[{l}i]" for l in labels)
                  if len(times) > 1 else f"[{n}:a]aresample=48000,volume={au.get('sfx_db', -22)}dB[{labels[0]}i]")
        for l, tt in zip(labels, times):
            ms = int(max(0, tt - (0.18 if kind == "whoosh" else 0)) * 1000)
            fc.append(f"[{l}i]adelay={ms}|{ms}[{l}]")
            mix.append(f"[{l}]")
        n += 1
    fc.append(f"{''.join(mix)}amix=inputs={len(mix)}:normalize=0:dropout_transition=0,"
              f"alimiter=limit=0.89:level=false,afade=t=out:st={max(0, total - 1.0):.3f}:d=1.0,"
              f"atrim=duration={total:.3f}[aout]")

    script = tmp / "filter.txt"
    script.write_text(";\n".join(fc))
    venc = (["-c:v", "libx264", "-preset", "ultrafast", "-crf", "28"] if preview else
            ["-c:v", "libx264", "-preset", preset, "-crf", str(crf), "-profile:v", "high", "-level", "4.2"])
    log(f"Compositing {len(res['broll'])} B-roll, {len(res['titles'])} titles, {len(res['subtitles'])} captions")
    ffmpeg(*inputs, "-filter_complex_script", str(script), "-map", f"[{cur}]", "-map", "[aout]",
           *venc, "-pix_fmt", "yuv420p", "-r", str(fps), "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
           "-t", f"{total:.3f}", "-movflags", "+faststart", str(out_path), timeout=7200)
    if not preview:
        write_srt(res, out_path.with_suffix(".srt"))
        shutil.copy(ass, out_path.with_suffix(".ass"))
    return out_path
