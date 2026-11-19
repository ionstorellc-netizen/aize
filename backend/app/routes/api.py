import json
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from pydantic import BaseModel
from sqlalchemy import func

from ..config import STORAGE, LIBRARY_DIR, REFERENCES_DIR
from ..db import (SessionLocal, Project, Stage, Job, ResearchRun, Competitor, Idea, Script, Asset,
                  IntegrationEvent, now)
from ..store import (get_setting, set_setting, reset_setting, SECRET_FIELDS, save_secret, secret_status, masked,
                     log_event)
from ..providers import claude, youtube, pexels, heygen, instagram
from ..agents import master
from ..agents.master import STAGES, enqueue, reset_from, project_dir
from ..engine import edl as E
from ..util import probe, ffmpeg, StageError

r = APIRouter(prefix="/api")


def media_url(path):
    if not path:
        return None
    p = Path(path).resolve()
    try:
        rel = p.relative_to(STORAGE.resolve())
    except ValueError:
        return None
    return f"/media/{rel.as_posix()}"


def ser_project(p: Project, full=False):
    d = p.data or {}
    out = {"id": p.id, "title": p.title, "topic": p.topic, "category": p.category, "status": p.status,
           "avatar_mode": p.avatar_mode, "cost_usd": round(p.cost_usd or 0, 4),
           "created_at": p.created_at.isoformat(), "updated_at": p.updated_at.isoformat(),
           "stages": [{"name": s.name, "label": dict(STAGES)[s.name], "status": s.status, "message": s.message,
                       "attempts": s.attempts, "output": s.output if full else None,
                       "started_at": s.started_at.isoformat() if s.started_at else None,
                       "finished_at": s.finished_at.isoformat() if s.finished_at else None} for s in p.stages],
           "script_id": d.get("script_id"), "idea_id": d.get("idea_id"), "research_run_id": d.get("research_run_id"),
           "recording_asset_id": d.get("recording_asset_id")}
    pdir = project_dir(p.id)
    exp = pdir / "export"
    mp4s = list(exp.glob("*.mp4")) if exp.exists() else []
    out["export"] = {"mp4": media_url(mp4s[0]), "srt": media_url(mp4s[0].with_suffix(".srt")),
                     "ass": media_url(mp4s[0].with_suffix(".ass")), "thumb": media_url(exp / "thumb.jpg")} if mp4s else None
    out["master"] = media_url(pdir / "master.mp4") if (pdir / "master.mp4").exists() else None
    out["preview"] = media_url(pdir / "preview.mp4") if (pdir / "preview.mp4").exists() else None
    out["avatar"] = media_url(pdir / "avatar.mp4") if (pdir / "avatar.mp4").exists() else None
    if full:
        out["data"] = {k: v for k, v in d.items() if k != "edl"}
        out["has_edl"] = "edl" in d
        qcf = pdir / "qc.json"
        out["qc"] = json.loads(qcf.read_text()) if qcf.exists() else None
        with SessionLocal() as s:
            jobs = s.query(Job).filter_by(project_id=p.id).order_by(Job.id.desc()).limit(5).all()
            out["jobs"] = [{"id": j.id, "kind": j.kind, "status": j.status, "error": j.error, "log": j.log[-6000:]}
                           for j in jobs]
    return out


# ------------------------------------------------------------------ dashboard

@r.get("/dashboard")
def dashboard():
    with SessionLocal() as s:
        projects = s.query(Project).order_by(Project.updated_at.desc()).all()
        cnt = lambda st: sum(1 for p in projects if p.status == st)
        failed_stages = s.query(Stage).filter_by(status="failed").count()
        rr = s.query(ResearchRun).filter_by(status="done").order_by(ResearchRun.id.desc()).first()
        comps = s.query(Competitor).order_by(Competitor.id.desc()).limit(6).all()
        cost = s.query(func.sum(IntegrationEvent.cost_usd)).scalar() or 0
        return {
            "totals": {"videos_produced": cnt("completed"), "processing": cnt("running"), "waiting": cnt("waiting"),
                       "completed_projects": cnt("completed"), "failed_jobs": cnt("failed"),
                       "failed_stages": failed_stages, "saved_scripts": s.query(Script).count(),
                       "projects": len(projects), "cost_usd": round(cost, 4)},
            "trending": ((rr.result or {}).get("insights", {}).get("trending_subjects") or
                         [o["title"] for o in (rr.result or {}).get("opportunities", [])[:6]]) if rr else [],
            "trending_source": f"research run #{rr.id} ({rr.created_at:%Y-%m-%d})" if rr else None,
            "competitors": [{"name": c.name, "platform": c.platform, "url": c.url, "followers": c.followers,
                             "verification": c.verification} for c in comps],
            "recent": [ser_project(p) for p in projects[:6]],
            "integrations": integration_status(),
        }


# ------------------------------------------------------------------ integrations

PROVIDERS = {
    "anthropic": ("Anthropic Claude", claude, "Ideas, scripts, B-roll matching, Roman Urdu polish, QC vision", "Pay-as-you-go (Opus 5.5: $4 / $20 per M tokens)"),
    "youtube": ("YouTube Data API v3", youtube, "Viral research and competitor metrics (verified)", "Free, 10,000 units/day (search = 100 units)"),
    "pexels": ("Pexels", pexels, "Licensed stock B-roll", "Free (Pexels License)"),
    "heygen": ("HeyGen", heygen, "AI avatar video (your Digital Twin + cloned voice)", "Paid plan with API access"),
    "instagram": ("Instagram Graph API", instagram, "Instagram competitor metrics (Business Discovery)", "Free; needs IG Business account + Meta app"),
}


def integration_status():
    out = []
    with SessionLocal() as s:
        for key, (label, mod, use, cost) in PROVIDERS.items():
            last_test = s.query(IntegrationEvent).filter_by(provider=key, kind="test").order_by(IntegrationEvent.id.desc()).first()
            calls = s.query(func.count(IntegrationEvent.id)).filter_by(provider=key, kind="call").scalar()
            units = s.query(func.sum(IntegrationEvent.units)).filter_by(provider=key, kind="call").scalar() or 0
            spend = s.query(func.sum(IntegrationEvent.cost_usd)).filter_by(provider=key).scalar() or 0
            errors = s.query(func.count(IntegrationEvent.id)).filter_by(provider=key, kind="error").scalar()
            configured = mod.configured()
            state = "not_configured"
            if configured:
                state = "configured_untested"
                if last_test:
                    state = "connected" if last_test.ok else "error"
            out.append({"key": key, "label": label, "use": use, "pricing": cost, "state": state,
                        "last_test": {"ok": bool(last_test.ok), "message": last_test.message,
                                      "at": last_test.created_at.isoformat()} if last_test else None,
                        "fields": [{"name": n, "secret": sec, "status": secret_status(n), "value": masked(n)}
                                   for n, sec in SECRET_FIELDS[key]],
                        "usage": {"calls": calls, "units": units, "cost_usd": round(spend, 4), "errors": errors}})
    out.append({"key": "whisper", "label": "Whisper (local, faster-whisper)", "use": "Transcription with word timing",
                "pricing": "Free, runs on your machine", "state": "local", "fields": [], "usage": {}})
    out.append({"key": "ffmpeg", "label": "FFmpeg + libass", "use": "Editing / rendering engine",
                "pricing": "Free, local", "state": "local" if shutil.which("ffmpeg") else "error", "fields": [], "usage": {}})
    out.append({"key": "tiktok", "label": "TikTok", "use": "Research", "pricing": "Research API restricted to approved researchers",
                "state": "unavailable", "fields": [], "usage": {}})
    return out


@r.get("/integrations")
def integrations():
    return integration_status()


class SecretIn(BaseModel):
    values: dict[str, str]


@r.put("/integrations/{key}")
def save_integration(key: str, body: SecretIn):
    allowed = {n for n, _ in SECRET_FIELDS.get(key, [])}
    if not allowed:
        raise HTTPException(404)
    for n, v in body.values.items():
        if n in allowed and not (v or "").startswith("••••"):
            save_secret(n, v.strip())
    return {"ok": True}


@r.post("/integrations/{key}/test")
def test_integration(key: str):
    if key not in PROVIDERS:
        raise HTTPException(404)
    mod = PROVIDERS[key][1]
    try:
        if not mod.configured():
            raise StageError("Not configured yet.")
        msg = mod.test()
        log_event(key, "test", True, msg)
        return {"ok": True, "message": msg}
    except Exception as e:
        log_event(key, "test", False, str(e))
        return {"ok": False, "message": str(e)}


@r.get("/integrations/events")
def integration_events(provider: str | None = None, limit: int = 100):
    with SessionLocal() as s:
        q = s.query(IntegrationEvent)
        if provider:
            q = q.filter_by(provider=provider)
        return [{"id": e.id, "provider": e.provider, "kind": e.kind, "ok": bool(e.ok), "message": e.message,
                 "units": e.units, "cost_usd": e.cost_usd, "at": e.created_at.isoformat()}
                for e in q.order_by(IntegrationEvent.id.desc()).limit(limit)]


# ------------------------------------------------------------------ research / competitors

class ResearchIn(BaseModel):
    query: str = ""
    categories: list[str] = []
    markets: list[str] = []


@r.post("/research")
def start_research(body: ResearchIn):
    with SessionLocal() as s:
        rr = ResearchRun(query=body.query, categories=body.categories, markets=body.markets)
        s.add(rr)
        s.commit()
        rid = rr.id
    jid = enqueue("research", run_id=rid)
    return {"id": rid, "job_id": jid}


@r.get("/research")
def list_research():
    with SessionLocal() as s:
        return [{"id": x.id, "query": x.query, "categories": x.categories, "markets": x.markets, "status": x.status,
                 "error": x.error, "created_at": x.created_at.isoformat(),
                 "videos": (x.result or {}).get("video_count"), "opportunities": len((x.result or {}).get("opportunities", []))}
                for x in s.query(ResearchRun).order_by(ResearchRun.id.desc()).limit(50)]


@r.get("/research/{rid}")
def get_research(rid: int):
    with SessionLocal() as s:
        x = s.get(ResearchRun, rid)
        if not x:
            raise HTTPException(404)
        return {"id": x.id, "query": x.query, "status": x.status, "error": x.error, "result": x.result,
                "created_at": x.created_at.isoformat()}


@r.get("/competitors")
def competitors():
    with SessionLocal() as s:
        return [{"id": c.id, "platform": c.platform, "name": c.name, "url": c.url, "followers": c.followers,
                 "source": c.source, "verification": c.verification, "data": c.data,
                 "created_at": c.created_at.isoformat()} for c in s.query(Competitor).order_by(Competitor.id.desc())]


class CompetitorIn(BaseModel):
    platform: str
    name: str
    url: str
    followers: int | None = None
    notes: str = ""
    top_video_url: str = ""
    top_video_views: int | None = None
    hook: str = ""
    format: str = ""


@r.post("/competitors")
def add_competitor(body: CompetitorIn):
    with SessionLocal() as s:
        c = Competitor(platform=body.platform, name=body.name, url=body.url, followers=body.followers,
                       source="manual", verification="unverified",
                       data={"notes": body.notes, "hook": body.hook, "format": body.format,
                             "top_videos": [{"url": body.top_video_url, "views": body.top_video_views,
                                             "label": "user-entered"}] if body.top_video_url else []})
        s.add(c)
        s.commit()
        return {"id": c.id}


@r.post("/competitors/instagram/{username}")
def add_instagram(username: str):
    try:
        d = instagram.business_discovery(username.lstrip("@"))
    except StageError as e:
        raise HTTPException(400, str(e))
    with SessionLocal() as s:
        c = Competitor(platform="Instagram", name=d["name"], url=d["url"], followers=d["followers"],
                       source="instagram_api", verification="verified", data=d)
        s.add(c)
        s.commit()
        return {"id": c.id}


@r.delete("/competitors/{cid}")
def del_competitor(cid: int):
    with SessionLocal() as s:
        c = s.get(Competitor, cid)
        if c:
            s.delete(c)
            s.commit()
    return {"ok": True}


# ------------------------------------------------------------------ ideas

class IdeasIn(BaseModel):
    topic: str = ""
    research_run_id: int | None = None
    category: str | None = None
    n: int = 10


@r.post("/ideas/generate")
def gen_ideas(body: IdeasIn):
    if not claude.configured():
        raise HTTPException(400, "Idea generation needs Claude (add ANTHROPIC_API_KEY in Integrations).")
    return {"job_id": enqueue("ideas", **body.model_dump())}


@r.get("/ideas")
def ideas(category: str | None = None, status: str | None = None):
    with SessionLocal() as s:
        q = s.query(Idea)
        if category:
            q = q.filter_by(category=category)
        if status:
            q = q.filter_by(status=status)
        return [{"id": i.id, "title": i.title, "category": i.category, "status": i.status, "data": i.data,
                 "research_run_id": i.research_run_id, "created_at": i.created_at.isoformat()}
                for i in q.order_by(Idea.id.desc()).limit(300)]


class IdeaManual(BaseModel):
    title: str
    category: str = "Amazon"
    topic: str = ""
    viral_hook: str = ""
    talking_points: list[str] = []


@r.post("/ideas")
def add_idea(body: IdeaManual):
    with SessionLocal() as s:
        i = Idea(title=body.title, category=body.category, data=body.model_dump() | {"source": "manual"})
        s.add(i)
        s.commit()
        return {"id": i.id}


class StatusIn(BaseModel):
    status: str


@r.patch("/ideas/{iid}")
def idea_status(iid: int, body: StatusIn):
    if body.status not in ("new", "approved", "rejected", "saved", "used"):
        raise HTTPException(400)
    with SessionLocal() as s:
        i = s.get(Idea, iid)
        i.status = body.status
        s.commit()
    return {"ok": True}


# ------------------------------------------------------------------ scripts

@r.get("/scripts")
def scripts():
    with SessionLocal() as s:
        return [{"id": x.id, "title": x.title, "status": x.status, "source": x.source, "project_id": x.project_id,
                 "idea_id": x.idea_id, "data": x.data, "updated_at": x.updated_at.isoformat()}
                for x in s.query(Script).order_by(Script.id.desc()).limit(200)]


class ScriptGen(BaseModel):
    idea_id: int | None = None
    topic: str = ""
    project_id: int | None = None
    notes: str = ""


@r.post("/scripts/generate")
def gen_script(body: ScriptGen):
    if not claude.configured():
        raise HTTPException(400, "Script generation needs Claude. Add ANTHROPIC_API_KEY or write the script manually.")
    idea = None
    if body.idea_id:
        with SessionLocal() as s:
            i = s.get(Idea, body.idea_id)
            idea = {"id": i.id, **(i.data or {})}
    return {"job_id": enqueue("script", project_id=body.project_id, idea=idea, topic=body.topic, notes=body.notes)}


class ScriptManual(BaseModel):
    title: str
    text: str
    project_id: int | None = None


@r.post("/scripts")
def new_script(body: ScriptManual):
    from ..agents.content import manual_script
    sid = manual_script(body.title, body.text, body.project_id)
    if body.project_id:
        master.Ctx(body.project_id).update(script_id=sid)
    return {"id": sid}


class ScriptEdit(BaseModel):
    title: str | None = None
    data: dict


@r.put("/scripts/{sid}")
def edit_script(sid: int, body: ScriptEdit):
    from ..agents.content import word_count
    with SessionLocal() as s:
        x = s.get(Script, sid)
        d = body.data
        if d.get("scenes"):
            d["spoken_full"] = " ".join(sc.get("spoken", "") for sc in d["scenes"])
            d["subtitle_transcript"] = [sc.get("spoken", "") for sc in d["scenes"]]
        d["word_count"] = word_count(d.get("spoken_full", ""))
        d["estimated_duration_s"] = round(d["word_count"] / 2.6, 1)
        x.data = d
        if body.title:
            x.title = body.title
        x.status = "draft"
        s.commit()
    return {"ok": True}


@r.post("/scripts/{sid}/approve")
def approve_script(sid: int):
    with SessionLocal() as s:
        x = s.get(Script, sid)
        x.status = "approved"
        s.commit()
        pid = x.project_id
    if pid:
        _continue_if_waiting(pid, "script_approval")
    return {"ok": True}


def _continue_if_waiting(pid, *stages):
    """Resume the pipeline if it is paused at one of `stages`."""
    with SessionLocal() as s:
        st = (s.query(Stage).filter(Stage.project_id == pid, Stage.name.in_(stages),
                                    Stage.status == "requires_approval").order_by(Stage.order).first())
        name = st.name if st else None
    if name:
        reset_from(pid, name)
        enqueue("pipeline", project_id=pid)


# ------------------------------------------------------------------ projects

class ProjectIn(BaseModel):
    title: str
    topic: str = ""
    category: str = ""
    avatar_mode: str = "own_recording"
    idea_id: int | None = None
    script_id: int | None = None
    research_run_id: int | None = None
    auto_start: bool = True


@r.post("/projects")
def create_project(body: ProjectIn):
    if body.avatar_mode not in ("heygen", "own_recording"):
        raise HTTPException(400, "avatar_mode must be heygen or own_recording")
    with SessionLocal() as s:
        data = {}
        if body.idea_id:
            i = s.get(Idea, body.idea_id)
            if i:
                data["idea_id"] = i.id
                i.status = "used"
                body.topic = body.topic or (i.data or {}).get("topic", i.title)
        if body.script_id:
            data["script_id"] = body.script_id
            sc = s.get(Script, body.script_id)
            if sc:
                data["topic_approved"] = True
        if body.research_run_id:
            data["research_run_id"] = body.research_run_id
        p = Project(title=body.title, topic=body.topic, category=body.category, avatar_mode=body.avatar_mode, data=data)
        master.create_stages(p)
        s.add(p)
        s.commit()
        pid = p.id
        if body.script_id:
            sc = s.get(Script, body.script_id)
            sc.project_id = pid
            s.commit()
    if body.auto_start:
        enqueue("pipeline", project_id=pid)
    return {"id": pid}


@r.get("/projects")
def list_projects(status: str | None = None):
    with SessionLocal() as s:
        q = s.query(Project)
        if status:
            q = q.filter_by(status=status)
        return [ser_project(p) for p in q.order_by(Project.updated_at.desc()).all()]


@r.get("/projects/{pid}")
def get_project(pid: int):
    with SessionLocal() as s:
        p = s.get(Project, pid)
        if not p:
            raise HTTPException(404)
        return ser_project(p, full=True)


class ProjectPatch(BaseModel):
    title: str | None = None
    topic: str | None = None
    category: str | None = None
    avatar_mode: str | None = None
    script_id: int | None = None
    cta: dict | None = None


@r.patch("/projects/{pid}")
def patch_project(pid: int, body: ProjectPatch):
    with SessionLocal() as s:
        p = s.get(Project, pid)
        for k in ("title", "topic", "category", "avatar_mode"):
            if getattr(body, k) is not None:
                setattr(p, k, getattr(body, k))
        d = dict(p.data or {})
        if body.script_id is not None:
            d["script_id"] = body.script_id
            sc = s.get(Script, body.script_id)
            if sc:
                sc.project_id = pid
        if body.cta is not None:
            d["cta"] = body.cta
        p.data = d
        s.commit()
    return {"ok": True}


@r.post("/projects/{pid}/start")
def start_project(pid: int):
    return {"job_id": enqueue("pipeline", project_id=pid)}


@r.post("/projects/{pid}/stages/{stage}/approve")
def approve_stage(pid: int, stage: str):
    ctx = master.Ctx(pid)
    if stage == "topic_approval":
        ctx.update(topic_approved=True)
    elif stage == "script_approval":
        sid = ctx.data().get("script_id")
        if sid:
            approve_script(sid)
            return {"ok": True}
    elif stage == "quality_control":
        ctx.update(qc_override=True)
        reset_from(pid, "export")
        _set_stage_completed(pid, "quality_control", "QC overridden by user")
        enqueue("pipeline", project_id=pid)
        return {"ok": True}
    elif stage == "export":
        ctx.update(final_approved=True)
    reset_from(pid, stage)
    enqueue("pipeline", project_id=pid)
    return {"ok": True}


def _set_stage_completed(pid, name, msg):
    with SessionLocal() as s:
        st = s.query(Stage).filter_by(project_id=pid, name=name).first()
        st.status, st.message, st.finished_at = "completed", msg, now()
        s.commit()


@r.post("/projects/{pid}/stages/{stage}/retry")
def retry_stage(pid: int, stage: str):
    if stage not in master.STAGE_NAMES:
        raise HTTPException(404)
    if stage in ("quality_control", "export", "audio_mixing"):
        master.Ctx(pid).update(final_approved=False, qc_override=False)
    reset_from(pid, stage)
    return {"job_id": enqueue("pipeline", project_id=pid)}


@r.post("/projects/{pid}/recording")
async def upload_recording(pid: int, file: UploadFile = File(...)):
    d = project_dir(pid)
    dest = d / f"recording_{datetime.now():%Y%m%d%H%M%S}{Path(file.filename or 'take.mp4').suffix.lower() or '.mp4'}"
    with open(dest, "wb") as fh:
        shutil.copyfileobj(file.file, fh)
    info = probe(dest)
    if not info["video"] or not info["audio"]:
        dest.unlink()
        raise HTTPException(400, "The file needs both video and audio.")
    with SessionLocal() as s:
        a = Asset(kind="avatar", path=str(dest), name=file.filename or dest.name, source="upload", project_id=pid,
                  duration=info["duration"], width=info["video"]["width"], height=info["video"]["height"])
        s.add(a)
        s.commit()
        aid = a.id
    master.Ctx(pid).update(recording_asset_id=aid)
    _continue_if_waiting(pid, "script_generation", "script_approval", "avatar_generation")
    return {"asset_id": aid, "duration": info["duration"]}


@r.post("/projects/{pid}/duplicate")
def duplicate(pid: int):
    with SessionLocal() as s:
        p = s.get(Project, pid)
        keep = {k: v for k, v in (p.data or {}).items() if k in ("idea_id", "research_run_id", "script_id", "topic_approved", "cta")}
        q = Project(title=p.title + " (copy)", topic=p.topic, category=p.category, avatar_mode=p.avatar_mode, data=keep)
        master.create_stages(q)
        s.add(q)
        s.commit()
        return {"id": q.id}


@r.delete("/projects/{pid}")
def delete_project(pid: int):
    with SessionLocal() as s:
        p = s.get(Project, pid)
        if p:
            s.delete(p)
            s.commit()
    shutil.rmtree(project_dir(pid), ignore_errors=True)
    return {"ok": True}


# ---- timeline editor

@r.get("/projects/{pid}/edl")
def get_edl(pid: int):
    d = master.Ctx(pid).data()
    if "edl" not in d:
        raise HTTPException(404, "This project has no edit yet (run it up to Video editing).")
    edl = d["edl"]
    for b in edl.get("broll", []):
        b["url"] = media_url(b["path"])
    res = E.resolved(edl)
    return {"edl": edl, "resolved": res, "avatar": media_url(project_dir(pid) / "avatar.mp4")}


class EdlIn(BaseModel):
    edl: dict


@r.put("/projects/{pid}/edl")
def put_edl(pid: int, body: EdlIn):
    edl = body.edl
    with SessionLocal() as s:
        for b in edl.get("broll", []):
            b.pop("url", None)
            if b.get("asset_id") and not b.get("path"):
                a = s.get(Asset, b["asset_id"])
                if not a:
                    raise HTTPException(400, f"B-roll asset {b['asset_id']} not found")
                b["path"] = a.path
    if edl.get("audio", {}).get("music") == "library" and edl["audio"].get("music_asset_id"):
        with SessionLocal() as s:
            a = s.get(Asset, edl["audio"]["music_asset_id"])
            edl["audio"]["music_path"] = a.path if a else None
    if not edl.get("segments"):
        raise HTTPException(400, "The edit needs at least one shot.")
    for sgm in edl["segments"]:
        if sgm["src_out"] <= sgm["src_in"]:
            raise HTTPException(400, f"Shot {sgm['id']} has zero or negative length.")
    master.Ctx(pid).update(edl=edl, final_approved=False, qc_override=False)
    # an edited timeline invalidates the master render and later stages
    with SessionLocal() as s:
        st = s.query(Stage).filter_by(project_id=pid, name="audio_mixing").first()
        if st and st.status != "pending":
            reset_from(pid, "audio_mixing")
    return {"ok": True, "duration": E.timeline_duration(edl)}


@r.post("/projects/{pid}/preview")
def preview(pid: int):
    if "edl" not in master.Ctx(pid).data():
        raise HTTPException(400, "No edit yet.")
    return {"job_id": enqueue("preview", project_id=pid)}


@r.post("/projects/{pid}/export")
def export(pid: int):
    reset_from(pid, "audio_mixing")
    master.Ctx(pid).update(final_approved=False, qc_override=False)
    return {"job_id": enqueue("pipeline", project_id=pid)}


# ------------------------------------------------------------------ jobs

@r.get("/jobs")
def jobs(limit: int = 50):
    with SessionLocal() as s:
        return [{"id": j.id, "kind": j.kind, "project_id": j.project_id, "status": j.status, "error": j.error,
                 "log": (j.log or "")[-3000:], "created_at": j.created_at.isoformat(),
                 "started_at": j.started_at.isoformat() if j.started_at else None,
                 "finished_at": j.finished_at.isoformat() if j.finished_at else None}
                for j in s.query(Job).order_by(Job.id.desc()).limit(limit)]


@r.get("/jobs/{jid}")
def job(jid: int):
    with SessionLocal() as s:
        j = s.get(Job, jid)
        if not j:
            raise HTTPException(404)
        return {"id": j.id, "kind": j.kind, "status": j.status, "error": j.error, "log": j.log}


# ------------------------------------------------------------------ assets / library

@r.get("/assets")
def assets(kind: str | None = None):
    with SessionLocal() as s:
        q = s.query(Asset)
        if kind:
            q = q.filter(Asset.kind.in_(kind.split(",")))
        return [{"id": a.id, "kind": a.kind, "name": a.name, "tags": a.tags, "source": a.source, "license": a.license,
                 "source_url": a.source_url, "duration": a.duration, "width": a.width, "height": a.height,
                 "project_id": a.project_id, "url": media_url(a.path), "created_at": a.created_at.isoformat()}
                for a in q.order_by(Asset.id.desc()).limit(500)]


@r.post("/assets")
async def upload_asset(file: UploadFile = File(...), kind: str = Form("broll"), tags: str = Form(""),
                       license: str = Form("Own footage")):
    if kind not in ("broll", "image", "music"):
        raise HTTPException(400)
    name = Path(file.filename or "upload").name
    dest = LIBRARY_DIR / f"{datetime.now():%Y%m%d%H%M%S}_{name}"
    with open(dest, "wb") as fh:
        shutil.copyfileobj(file.file, fh)
    try:
        info = probe(dest)
    except StageError:
        dest.unlink()
        raise HTTPException(400, "Unsupported media file.")
    v = info["video"] or {}
    with SessionLocal() as s:
        a = Asset(kind=kind, path=str(dest), name=Path(name).stem.replace("_", " "),
                  tags=[t.strip().lower() for t in tags.split(",") if t.strip()], source="upload", license=license,
                  duration=info["duration"] or None, width=v.get("width"), height=v.get("height"))
        s.add(a)
        s.commit()
        return {"id": a.id}


class AssetPatch(BaseModel):
    name: str | None = None
    tags: list[str] | None = None


@r.patch("/assets/{aid}")
def patch_asset(aid: int, body: AssetPatch):
    with SessionLocal() as s:
        a = s.get(Asset, aid)
        if body.name is not None:
            a.name = body.name
        if body.tags is not None:
            a.tags = [t.lower() for t in body.tags]
        s.commit()
    return {"ok": True}


@r.delete("/assets/{aid}")
def delete_asset(aid: int):
    with SessionLocal() as s:
        a = s.get(Asset, aid)
        if a:
            if a.source == "upload" and Path(a.path).is_relative_to(LIBRARY_DIR):
                Path(a.path).unlink(missing_ok=True)
            s.delete(a)
            s.commit()
    return {"ok": True}


@r.get("/stock/search")
def stock_search(q: str):
    try:
        return pexels.search(q, per_page=12)
    except StageError as e:
        raise HTTPException(400, str(e))


class StockImport(BaseModel):
    item: dict


@r.post("/stock/import")
def stock_import(body: StockImport):
    it = body.item
    dest = LIBRARY_DIR / f"pexels_{it['id']}.mp4"
    try:
        pexels.download(it, dest)
    except Exception as e:
        raise HTTPException(400, f"Download failed: {e}")
    info = probe(dest)
    with SessionLocal() as s:
        a = Asset(kind="broll", path=str(dest), name=it.get("query", "stock"), tags=it.get("query", "").lower().split(),
                  source="pexels", license=it.get("license", "Pexels License"), source_url=it.get("url", ""),
                  duration=info["duration"], width=(info["video"] or {}).get("width"), height=(info["video"] or {}).get("height"))
        s.add(a)
        s.commit()
        return {"id": a.id, "url": media_url(dest), "path": str(dest)}


# ------------------------------------------------------------------ settings

@r.get("/settings/{key}")
def get_settings(key: str):
    if key not in ("style_profile", "avatar_profile", "preferences"):
        raise HTTPException(404)
    v = get_setting(key)
    if key == "avatar_profile":
        ref = REFERENCES_DIR / "avatar_ref.jpg"
        v["_reference_frame"] = media_url(ref) if ref.exists() else None
        pv = REFERENCES_DIR / "avatar_preview.mp4"
        v["_reference_video"] = media_url(pv) if pv.exists() else None
    if key == "style_profile":
        pv = REFERENCES_DIR / "style_preview.mp4"
        v["_reference_video"] = media_url(pv) if pv.exists() else None
    return v


class SettingsIn(BaseModel):
    value: dict


@r.put("/settings/{key}")
def put_settings(key: str, body: SettingsIn):
    if key not in ("style_profile", "avatar_profile", "preferences"):
        raise HTTPException(404)
    set_setting(key, {k: v for k, v in body.value.items() if not k.startswith("_")})
    return {"ok": True}


@r.post("/settings/{key}/reset")
def reset_settings(key: str):
    reset_setting(key)
    return {"ok": True}


@r.post("/settings/reference/{which}")
async def upload_reference(which: str, file: UploadFile = File(...)):
    if which not in ("avatar", "style"):
        raise HTTPException(404)
    ext = Path(file.filename or "ref.mp4").suffix.lower() or ".mp4"
    for old in REFERENCES_DIR.glob(f"{which}_reference.*"):
        old.unlink()
    dest = REFERENCES_DIR / f"{which}_reference{ext}"
    with open(dest, "wb") as fh:
        shutil.copyfileobj(file.file, fh)
    info = probe(dest)
    # browser-safe H.264 proxy for the reference players (phones often record HEVC)
    ffmpeg("-i", str(dest), "-vf", "scale=540:-2", "-c:v", "libx264", "-preset", "veryfast", "-crf", "26",
           "-c:a", "aac", "-b:a", "96k", "-movflags", "+faststart", str(REFERENCES_DIR / f"{which}_preview.mp4"))
    if which == "avatar":
        extract_reference_frame(dest)
        prof = get_setting("avatar_profile")
        prof["reference_file"] = file.filename
        prof.setdefault("observed", {})["source"] = (f"{(info['video'] or {}).get('codec')} {(info['video'] or {}).get('width')}x"
                                                     f"{(info['video'] or {}).get('height')} @{(info['video'] or {}).get('fps')}fps, {info['duration']:.1f}s")
        set_setting("avatar_profile", prof)
    return {"ok": True, "duration": info["duration"]}


def extract_reference_frame(video):
    ffmpeg("-ss", "2", "-i", str(video), "-frames:v", "1", "-vf", "scale=720:-2", str(REFERENCES_DIR / "avatar_ref.jpg"))


# ------------------------------------------------------------------ analytics

@r.get("/analytics")
def analytics():
    with SessionLocal() as s:
        projects = s.query(Project).all()
        stages = s.query(Stage).all()
        days = {}
        start = datetime.now(timezone.utc).date() - timedelta(days=29)
        for i in range(30):
            days[(start + timedelta(days=i)).isoformat()] = {"created": 0, "completed": 0}
        for p in projects:
            k = p.created_at.date().isoformat()
            if k in days:
                days[k]["created"] += 1
            if p.status == "completed":
                k2 = p.updated_at.date().isoformat()
                if k2 in days:
                    days[k2]["completed"] += 1
        stage_stats = {}
        for st in stages:
            d = stage_stats.setdefault(st.name, {"completed": 0, "failed": 0, "attempts": 0, "seconds": []})
            if st.status == "completed":
                d["completed"] += 1
            if st.status == "failed":
                d["failed"] += 1
            d["attempts"] += st.attempts or 0
            if st.started_at and st.finished_at and st.status == "completed":
                d["seconds"].append((st.finished_at - st.started_at).total_seconds())
        for d in stage_stats.values():
            secs = d.pop("seconds")
            d["avg_seconds"] = round(sum(secs) / len(secs), 1) if secs else None
        cost = {}
        for e in s.query(IntegrationEvent).filter(IntegrationEvent.cost_usd > 0):
            cost[e.provider] = round(cost.get(e.provider, 0) + e.cost_usd, 4)
        durations = []
        for p in projects:
            if p.status == "completed":
                qcf = project_dir(p.id) / "qc.json"
                if qcf.exists():
                    durations.append({"id": p.id, "title": p.title, "duration": json.loads(qcf.read_text()).get("duration")})
        return {"daily": [{"date": k, **v} for k, v in days.items()], "stages": stage_stats, "cost_by_provider": cost,
                "durations": durations, "projects_total": len(projects),
                "note": "Production analytics. Published-video performance needs the platform APIs for your own accounts."}
