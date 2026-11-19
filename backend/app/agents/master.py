"""Master Agent: drives every project through 12 stages, persists each stage's output,
pauses at approval gates, and resumes/retries from any stage without redoing finished work."""
import json
import shutil
import threading
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

from ..config import PROJECTS_DIR, REFERENCES_DIR, WORKER_THREADS
from ..db import SessionLocal, Project, Stage, Job, Script, Idea, ResearchRun, Asset, now
from ..store import get_setting
from ..providers import claude, heygen, youtube
from ..engine import transcribe as T, edl as E, render as R
from ..util import StageError, write_json, has_non_roman
from . import research, content, broll, qc
from .schemas import CutChoice, SubtitleFix

STAGES = [
    ("research", "Research"),
    ("competitor_analysis", "Competitor analysis"),
    ("topic_approval", "Topic approval"),
    ("script_generation", "Script generation"),
    ("script_approval", "Script approval"),
    ("avatar_generation", "Avatar generation"),
    ("broll_selection", "B-roll selection"),
    ("video_editing", "Video editing"),
    ("subtitle_generation", "Subtitle generation"),
    ("audio_mixing", "Audio mixing + master render"),
    ("quality_control", "Quality control"),
    ("export", "Export"),
]
STAGE_NAMES = [s for s, _ in STAGES]


class NeedsApproval(Exception):
    def __init__(self, message, output=None):
        super().__init__(message)
        self.output = output or {}


class Skip(Exception):
    pass


def project_dir(pid):
    d = PROJECTS_DIR / str(pid)
    d.mkdir(parents=True, exist_ok=True)
    return d


def create_stages(project):
    project.stages = [Stage(name=n, order=i) for i, (n, _) in enumerate(STAGES)]


# ------------------------------------------------------------------ context helpers

class Ctx:
    def __init__(self, pid, job_id=None):
        self.pid, self.job_id = pid, job_id
        self.dir = project_dir(pid)

    def project(self):
        with SessionLocal() as s:
            return s.get(Project, self.pid)

    def data(self):
        return dict(self.project().data or {})

    def update(self, **kw):
        with SessionLocal() as s:
            p = s.get(Project, self.pid)
            d = dict(p.data or {})
            d.update(kw)
            p.data = d
            s.commit()

    def stage_output(self, name):
        with SessionLocal() as s:
            st = s.query(Stage).filter_by(project_id=self.pid, name=name).first()
            return dict(st.output or {}) if st else {}

    def log(self, msg):
        line = f"[{datetime.now(timezone.utc).strftime('%H:%M:%S')}] {msg}"
        print(f"project {self.pid}: {msg}", flush=True)
        if self.job_id:
            with SessionLocal() as s:
                j = s.get(Job, self.job_id)
                if j:
                    j.log = ((j.log or "") + line + "\n")[-20000:]
                    s.commit()


def approved_script(ctx):
    d = ctx.data()
    if not d.get("script_id"):
        return None
    with SessionLocal() as s:
        sc = s.get(Script, d["script_id"])
        return (sc.status, sc.data, sc.id) if sc else None


# ------------------------------------------------------------------ stages

def st_research(ctx):
    d = ctx.data()
    if d.get("research_run_id"):
        with SessionLocal() as s:
            rr = s.get(ResearchRun, d["research_run_id"])
            if rr and rr.status == "done":
                return f"Using research run #{rr.id} ({rr.result.get('video_count', 0)} verified videos)", {"research_run_id": rr.id}
    if not youtube.configured():
        raise Skip("No research provider configured (add YOUTUBE_API_KEY). Topic used as entered.")
    p = ctx.project()
    with SessionLocal() as s:
        rr = ResearchRun(query=p.topic or p.title, categories=[p.category] if p.category else [], markets=[])
        s.add(rr)
        s.commit()
        rid = rr.id
    research.run(rid, log=ctx.log)
    ctx.update(research_run_id=rid)
    return f"Research run #{rid} complete", {"research_run_id": rid}


def st_competitors(ctx):
    rid = ctx.data().get("research_run_id")
    if not rid:
        raise Skip("No research data for this project.")
    with SessionLocal() as s:
        rr = s.get(ResearchRun, rid)
        comps = (rr.result or {}).get("competitors", [])[:10]
    return f"{len(comps)} competitor accounts analysed (verified YouTube metrics)", {
        "competitors": [{k: c.get(k) for k in ("name", "url", "followers", "found_views", "top_videos")} for c in comps]}


def st_topic(ctx):
    d = ctx.data()
    if d.get("idea_id") or d.get("topic_approved"):
        return "Topic approved", {"topic": ctx.project().topic}
    raise NeedsApproval("Approve the topic (or pick one of the research ideas) to continue.",
                        {"topic": ctx.project().topic})


def st_script(ctx):
    d = ctx.data()
    sc = approved_script(ctx)
    if sc:
        return f"Script #{sc[2]} attached", {"script_id": sc[2]}
    p = ctx.project()
    if p.avatar_mode == "own_recording" and d.get("recording_asset_id") and not claude.configured():
        raise Skip("Using your uploaded recording as-is (no script needed).")
    if not claude.configured():
        raise NeedsApproval("Claude is not configured: write or paste the script in Script Studio and attach it to this project.")
    idea = None
    if d.get("idea_id"):
        with SessionLocal() as s:
            i = s.get(Idea, d["idea_id"])
            idea = {"id": i.id, **(i.data or {})} if i else None
    sid = content.generate_script(idea=idea, topic=p.topic or p.title, project_id=p.id, log=ctx.log)
    ctx.update(script_id=sid)
    return f"Script #{sid} generated", {"script_id": sid}


def st_script_approval(ctx):
    sc = approved_script(ctx)
    if sc is None:
        p = ctx.project()
        if p.avatar_mode == "own_recording" and ctx.data().get("recording_asset_id"):
            raise Skip("No script: editing your recording directly.")
        raise NeedsApproval("Attach a script to this project.")
    if sc[0] == "approved":
        return "Script approved", {"script_id": sc[2]}
    raise NeedsApproval("Review and approve the script in Script Studio.", {"script_id": sc[2]})


def st_avatar(ctx):
    p, d = ctx.project(), ctx.data()
    prefs = get_setting("preferences")
    raw = ctx.dir / "avatar_raw.mp4"
    if p.avatar_mode == "heygen":
        if not heygen.configured():
            raise StageError("HeyGen is not configured (API key, avatar_id, voice_id). Switch this project to "
                             "'Own recording' and upload a take, or add HeyGen in Integrations.")
        sc = approved_script(ctx)
        if not sc:
            raise StageError("An approved script is required for avatar generation.")
        vid = d.get("heygen_video_id")
        if not vid:
            vid = heygen.generate(sc[1]["spoken_full"], project_id=p.id)
            ctx.update(heygen_video_id=vid)
        ctx.log(f"HeyGen video {vid} rendering")
        heygen.wait(vid, raw, project_id=p.id, on_status=lambda s_: ctx.log(f"HeyGen status: {s_}"))
        with SessionLocal() as s:
            s.add(Asset(kind="avatar", path=str(raw), name=f"HeyGen {vid}", source="heygen", project_id=p.id))
            s.commit()
    else:
        aid = d.get("recording_asset_id")
        if not aid:
            raise NeedsApproval("Upload your recording for this project (Production Queue > project > Upload recording), then continue.")
        with SessionLocal() as s:
            a = s.get(Asset, aid)
            src = a.path
        raw = Path(src)
    norm = ctx.dir / "avatar.mp4"
    ctx.log("Normalising avatar video to 1080x1920 / 30 fps")
    R.normalize_source(raw, norm)
    ctx.log("Transcribing (word timestamps, Roman script)")
    tr = T.transcribe(norm, ctx.dir, roman=prefs.get("language") == "roman_urdu", prompt=prefs.get("whisper_prompt"))
    write_json(ctx.dir / "transcript.json", tr)
    return f"Avatar video ready ({tr['duration']:.1f}s, {len(tr['words'])} words transcribed)", {
        "avatar_path": str(norm), "transcript_path": str(ctx.dir / "transcript.json"), "words": len(tr["words"])}


def _transcript(ctx):
    return json.loads((ctx.dir / "transcript.json").read_text())


def st_broll(ctx):
    style = get_setting("style_profile")
    sc = approved_script(ctx)
    items = broll.plan(_transcript(ctx), ctx.dir, style, script=sc[1] if sc else None, project_id=ctx.pid, log=ctx.log)
    write_json(ctx.dir / "broll_plan.json", items)
    return f"{len(items)} B-roll picks", {"count": len(items), "sources": {k: sum(1 for i in items if i["source"] == k)
                                                                          for k in ("library", "pexels", "generated")}}


def st_edit(ctx):
    style, prefs = get_setting("style_profile"), get_setting("preferences")
    tr = _transcript(ctx)
    sc = approved_script(ctx)
    sdata = sc[1] if sc else {}
    plan_items = json.loads((ctx.dir / "broll_plan.json").read_text()) if (ctx.dir / "broll_plan.json").exists() else []
    max_d = prefs["default_duration_s"][1]
    keep = None
    sents = E.sentences(E.remove_stutters(tr["words"]))
    talk = sum(s["e"] - s["s"] + 0.1 for s in sents)
    if talk > max_d and claude.configured():
        ctx.log(f"Talk is {talk:.0f}s; asking the editor model which sentences to keep for <= {max_d}s")
        res = claude.structured(
            "You are a short-form video editor. Choose which sentences to keep so the cut is coherent, keeps the hook "
            "and the conclusion/CTA, removes repetition and bad takes, and stays under the duration limit.",
            json.dumps({"limit_s": max_d - 1, "sentences": [{"id": s["id"], "text": s["text"],
                                                             "dur": round(s["e"] - s["s"], 2)} for s in sents]},
                       ensure_ascii=False), CutChoice, project_id=ctx.pid, purpose="cut_selection", effort="low")
        keep = res.keep_sentence_ids
    hook = {"text": sdata.get("hook_title") or ctx.project().title, "sub": sdata.get("hook_subtitle", "")}
    kw = (sdata.get("cta_keyword") or "").upper()
    cta = {"text": sdata.get("cta") if sdata.get("cta") and len(sdata.get("cta", "")) < 70 else
           (f'Comment "{kw}" for the full guide' if kw else None), "sub": kw or None}
    if not cta["text"]:
        cta = ctx.data().get("cta") or {}
    edl = E.build(tr, style, ctx.dir / "avatar.mp4", script=sdata, broll_plan=plan_items, cta=cta,
                  max_duration=max_d, keep_sentence_ids=keep, hook=hook)
    low = [w["w"] for w in tr["words"] if w.get("p", 1) < 0.25]
    edl["_low_confidence_words"] = low[:40]
    ctx.update(edl=edl)
    write_json(ctx.dir / "edl.json", edl)
    return (f"Edit built: {E.timeline_duration(edl):.1f}s, {len(edl['segments'])} shots, {len(edl['broll'])} B-roll, "
            f"{len(edl['titles'])} titles"), {"duration": E.timeline_duration(edl), "dropped": edl["dropped_sentences"]}


def st_subtitles(ctx):
    edl = ctx.data()["edl"]
    subs = edl["subtitles"]
    polished = False
    if claude.configured() and subs:
        sc = approved_script(ctx)
        ref = sc[1].get("spoken_full", "") if sc else ""
        payload = [{"id": i, "words": [w["w"] for w in ph["words"]]} for i, ph in enumerate(subs)]
        res = claude.structured(
            "You correct Roman Urdu subtitles produced by speech recognition. Return every phrase with the SAME number "
            "of words in the same order. Fix spelling to natural Roman Urdu (e.g. 'zaroori', 'chahte hain', 'sabse'), "
            "keep English e-commerce terms in English, keep punctuation light. Latin script only. If a script is given, "
            "use it as the spelling reference but never add or drop words.",
            json.dumps({"script_reference": ref, "phrases": payload}, ensure_ascii=False), SubtitleFix,
            project_id=ctx.pid, purpose="subtitle_polish", effort="low")
        fixes = {f.id: f.words for f in res.phrases}
        changed = 0
        for i, ph in enumerate(subs):
            nw = fixes.get(i)
            if nw and len(nw) == len(ph["words"]) and not any(has_non_roman(x) for x in nw):
                for w, x in zip(ph["words"], nw):
                    if w["w"] != x:
                        changed += 1
                    w["w"] = x
        polished = True
        ctx.log(f"Claude polished {changed} subtitle words")
    edl["_subtitles_polished"] = polished
    bad = [w["w"] for ph in subs for w in ph["words"] if has_non_roman(w["w"])]
    ctx.update(edl=edl)
    write_json(ctx.dir / "edl.json", edl)
    if bad:
        raise StageError(f"Subtitles contain non-Roman script: {bad[:6]}. Fix them in the Video Editor.")
    return f"{len(subs)} Roman Urdu captions{' (Claude-polished)' if polished else ''}", {"captions": len(subs), "polished": polished}


def _music_path(prefs):
    a_id = (prefs.get("audio") or {}).get("music_asset_id")
    if a_id:
        with SessionLocal() as s:
            a = s.get(Asset, a_id)
            if a:
                return a.path
    return None


def st_audio_render(ctx):
    style, prefs = get_setting("style_profile"), get_setting("preferences")
    edl = ctx.data()["edl"]
    out = ctx.dir / "master.mp4"
    R.render(edl, style, ctx.dir, out, preview=False, music_path=_music_path(prefs), log=ctx.log,
             crf=prefs["export"].get("crf", 18), preset=prefs["export"].get("preset", "medium"))
    from ..util import loudness
    ld = loudness(out)
    return f"Master rendered: {ld['integrated_lufs']} LUFS, peak {ld['true_peak_db']} dBTP", {
        "master": str(out), "srt": str(out.with_suffix(".srt")), "loudness": ld}


def st_qc(ctx):
    style, prefs = get_setting("style_profile"), get_setting("preferences")
    edl = ctx.data()["edl"]
    ref = REFERENCES_DIR / "avatar_ref.jpg"
    rep = qc.run_qc(ctx.dir / "master.mp4", edl, style, prefs, ref, ctx.project().avatar_mode, ctx.dir, ctx.pid)
    write_json(ctx.dir / "qc.json", rep)
    if not rep["passed"] and not ctx.data().get("qc_override"):
        raise NeedsApproval("QC flagged critical issues: " + ", ".join(rep["critical_failures"]) +
                            ". Fix them in the Video Editor and re-render, or approve to override.", rep)
    n = sum(1 for c in rep["checks"] if c["status"] == "pass")
    return f"QC {'passed' if rep['passed'] else 'overridden'}: {n}/{len(rep['checks'])} checks pass", rep


def st_export(ctx):
    prefs = get_setting("preferences")
    d = ctx.data()
    if prefs.get("require_final_approval", True) and not d.get("final_approved"):
        raise NeedsApproval("Preview the master and approve the final export.")
    p = ctx.project()
    exp = ctx.dir / "export"
    exp.mkdir(exist_ok=True)
    slug = "".join(c if c.isalnum() else "_" for c in p.title)[:50].strip("_") or f"project_{p.id}"
    final = exp / f"{slug}.mp4"
    shutil.copy(ctx.dir / "master.mp4", final)
    for ext in (".srt", ".ass"):
        if (ctx.dir / f"master{ext}").exists():
            shutil.copy(ctx.dir / f"master{ext}", final.with_suffix(ext))
    from ..util import ffmpeg
    ffmpeg("-ss", "1.0", "-i", str(final), "-frames:v", "1", "-vf", "scale=540:-2", str(exp / "thumb.jpg"))
    with SessionLocal() as s:
        s.add(Asset(kind="render", path=str(final), name=p.title, source="engine", project_id=p.id))
        s.commit()
    return "Exported MP4 + subtitles", {"mp4": str(final), "srt": str(final.with_suffix(".srt")),
                                         "ass": str(final.with_suffix(".ass")), "thumb": str(exp / "thumb.jpg")}


HANDLERS = {"research": st_research, "competitor_analysis": st_competitors, "topic_approval": st_topic,
            "script_generation": st_script, "script_approval": st_script_approval, "avatar_generation": st_avatar,
            "broll_selection": st_broll, "video_editing": st_edit, "subtitle_generation": st_subtitles,
            "audio_mixing": st_audio_render, "quality_control": st_qc, "export": st_export}


# ------------------------------------------------------------------ pipeline

def _set_stage(pid, name, **kw):
    with SessionLocal() as s:
        st = s.query(Stage).filter_by(project_id=pid, name=name).first()
        for k, v in kw.items():
            setattr(st, k, v)
        s.commit()


def _set_project(pid, **kw):
    with SessionLocal() as s:
        p = s.get(Project, pid)
        for k, v in kw.items():
            setattr(p, k, v)
        s.commit()


def run_pipeline(pid, job_id=None):
    ctx = Ctx(pid, job_id)
    _set_project(pid, status="running")
    with SessionLocal() as s:
        stages = [(st.name, st.status) for st in s.query(Stage).filter_by(project_id=pid).order_by(Stage.order)]
    for name, status in stages:
        if status in ("completed", "skipped"):
            continue
        _set_stage(pid, name, status="processing", started_at=now(), message="", attempts=Stage.attempts + 1)
        ctx.log(f"Stage {name}: started")
        try:
            msg, out = HANDLERS[name](ctx)
            _set_stage(pid, name, status="completed", message=msg, output=out, finished_at=now())
            ctx.log(f"Stage {name}: {msg}")
        except Skip as e:
            _set_stage(pid, name, status="skipped", message=str(e), finished_at=now())
            ctx.log(f"Stage {name}: skipped ({e})")
        except NeedsApproval as e:
            _set_stage(pid, name, status="requires_approval", message=str(e), output=e.output)
            _set_project(pid, status="waiting")
            ctx.log(f"Stage {name}: waiting for approval")
            return
        except Exception as e:
            msg = str(e) if isinstance(e, StageError) else f"{type(e).__name__}: {e}"
            _set_stage(pid, name, status="failed", message=msg, finished_at=now())
            _set_project(pid, status="failed")
            ctx.log(f"Stage {name} FAILED: {msg}\n{traceback.format_exc()[-1500:]}")
            return
    _set_project(pid, status="completed")


def reset_from(pid, name):
    """Mark `name` and every later stage pending (completed earlier stages are reused)."""
    idx = STAGE_NAMES.index(name)
    with SessionLocal() as s:
        for st in s.query(Stage).filter_by(project_id=pid):
            if st.order >= idx:
                st.status, st.message = "pending", ""
        s.commit()


# ------------------------------------------------------------------ job queue + workers

def enqueue(kind, project_id=None, **payload):
    with SessionLocal() as s:
        j = Job(kind=kind, project_id=project_id, payload=payload)
        s.add(j)
        s.commit()
        return j.id


_claim = threading.Lock()


def _claim_job():
    with _claim, SessionLocal() as s:
        busy_projects = {j.project_id for j in s.query(Job).filter_by(status="running") if j.project_id}
        for j in s.query(Job).filter_by(status="queued").order_by(Job.id):
            if j.project_id and j.project_id in busy_projects:
                continue
            j.status, j.started_at = "running", now()
            s.commit()
            return j.id, j.kind, j.project_id, dict(j.payload or {})
    return None


def _execute(job_id, kind, pid, payload):
    log = lambda m: Ctx(pid or 0, job_id).log(m) if pid else print(m)
    if kind == "pipeline":
        run_pipeline(pid, job_id)
    elif kind == "research":
        research.run(payload["run_id"], log=lambda m: _job_log(job_id, m))
    elif kind == "ideas":
        content.generate_ideas(payload.get("topic", ""), payload.get("research_run_id"), payload.get("category"),
                               payload.get("n", 10), log=lambda m: _job_log(job_id, m))
    elif kind == "script":
        sid = content.generate_script(idea=payload.get("idea"), topic=payload.get("topic", ""),
                                      project_id=pid, notes=payload.get("notes", ""))
        if pid:
            Ctx(pid).update(script_id=sid)
        _job_log(job_id, f"script #{sid} created")
    elif kind == "preview":
        ctx = Ctx(pid, job_id)
        edl = ctx.data()["edl"]
        R.render(edl, get_setting("style_profile"), ctx.dir, ctx.dir / "preview.mp4", preview=True,
                 music_path=_music_path(get_setting("preferences")), log=ctx.log)
        ctx.update(preview_rendered_at=time.time())
    else:
        raise StageError(f"unknown job kind {kind}")


def _job_log(job_id, m):
    with SessionLocal() as s:
        j = s.get(Job, job_id)
        if j:
            j.log = ((j.log or "") + m + "\n")[-20000:]
            s.commit()


def worker_loop(stop: threading.Event):
    while not stop.is_set():
        c = _claim_job()
        if not c:
            stop.wait(1.0)
            continue
        job_id, kind, pid, payload = c
        status, err = "done", ""
        try:
            _execute(job_id, kind, pid, payload)
        except Exception as e:
            status, err = "failed", str(e) if isinstance(e, StageError) else f"{type(e).__name__}: {e}"
            _job_log(job_id, traceback.format_exc()[-2000:])
        with SessionLocal() as s:
            j = s.get(Job, job_id)
            j.status, j.error, j.finished_at = status, err, now()
            s.commit()


def start_workers():
    # jobs that were running when the server stopped go back to the queue (stage outputs are already saved)
    with SessionLocal() as s:
        for j in s.query(Job).filter_by(status="running"):
            j.status = "queued"
        for st in s.query(Stage).filter_by(status="processing"):
            st.status = "pending"
        s.commit()
    stop = threading.Event()
    for i in range(WORKER_THREADS):
        threading.Thread(target=worker_loop, args=(stop,), daemon=True, name=f"worker-{i}").start()
    return stop
