"""Idea generator + Script agent (Claude)."""
import json
import re

from ..db import SessionLocal, Idea, Script, ResearchRun
from ..providers import claude
from ..util import StageError, has_non_roman
from .schemas import IdeaList, ScriptOut

VOICE = """Creator voice: a Pakistani e-commerce mentor speaking natural conversational Urdu/Hindi written in
ROMAN URDU (Latin letters only, never Urdu or Devanagari script). Keep English e-commerce terms in English:
Amazon FBA, Amazon FBM, Private Label, Product Hunting, PPC, Shopify, Wholesale, Sourcing, AI Automation,
Seller Central, listing, supplier, profit margin. Natural spelling, e.g. "Agar aap Amazon pe business start
karna chahte hain, to yeh mistake mat karna." Energetic, direct to camera, short sentences."""

IDEAS_SYSTEM = f"""You are the Viral Content Idea Generator for an e-commerce education channel.
{VOICE}
Use the research data provided. competitor_inspiration_urls must be copied exactly from the provided source urls
(or be empty if none fit). Ideas must be factually sound and teachable in 30-50 seconds. No income guarantees."""

SCRIPT_SYSTEM = f"""You are the Script Agent. Write a 30-50 second short-form script for the creator's AI avatar.
{VOICE}
Structure (seconds): 0-3 powerful hook; 3-12 problem or curiosity; 12-30 main educational value;
30-42 key insight or payoff; 42-50 engagement CTA (comment a keyword).
Speaking rate is about 2.6 words per second, so total spoken words must be 80-125.
Every scene needs 2-3 concrete stock-footage queries in English that literally show what is being said
(e.g. "amazon warehouse conveyor", "yiwu market shop stalls", "factory production line packaging").
Be factually accurate; put any claim that needs checking (fees, numbers, policies) in fact_check_notes.
Never claim fake results, earnings or fake screenshots."""


def generate_ideas(topic="", research_run_id=None, category=None, n=10, log=print):
    if not claude.configured():
        raise StageError("Idea generation needs Claude (add ANTHROPIC_API_KEY in Integrations).")
    ctx = {}
    if research_run_id:
        with SessionLocal() as s:
            rr = s.get(ResearchRun, research_run_id)
            if rr and rr.result:
                ctx = {"opportunities": rr.result.get("opportunities", [])[:20],
                       "insights": rr.result.get("insights", {}),
                       "competitors": [{k: c.get(k) for k in ("name", "url", "followers", "top_videos")}
                                       for c in rr.result.get("competitors", [])[:10]]}
    prompt = f"Generate {n} video ideas."
    if topic:
        prompt += f"\nRequested topic: {topic}"
    if category:
        prompt += f"\nCategory filter: {category}"
    prompt += f"\nRESEARCH DATA (verified metrics, may be empty):\n{json.dumps(ctx, ensure_ascii=False)[:60000]}"
    res = claude.structured(IDEAS_SYSTEM, prompt, IdeaList, purpose="ideas")
    valid = set()
    for o in ctx.get("opportunities", []):
        valid |= set(o.get("source_urls", []))
    created = []
    with SessionLocal() as s:
        for i in res.ideas:
            d = i.model_dump()
            d["competitor_inspiration_urls"] = [u for u in d["competitor_inspiration_urls"] if u in valid]
            row = Idea(title=i.title, category=i.category, data=d, research_run_id=research_run_id)
            s.add(row)
            s.flush()
            created.append(row.id)
        s.commit()
    return created


def word_count(text):
    return len(re.findall(r"\S+", text))


def generate_script(idea=None, topic="", project_id=None, notes="", log=print):
    if not claude.configured():
        raise StageError("Script generation needs Claude. Add ANTHROPIC_API_KEY, or write the script manually in Script Studio.")
    brief = {"topic": topic}
    if idea:
        brief.update(idea)
    prompt = f"BRIEF:\n{json.dumps(brief, ensure_ascii=False)}\n{('Extra notes: ' + notes) if notes else ''}"
    out = None
    for attempt in range(2):
        out = claude.structured(SCRIPT_SYSTEM, prompt, ScriptOut, project_id=project_id, purpose="script")
        spoken = " ".join(sc.spoken for sc in out.scenes)
        wc = word_count(spoken)
        if not has_non_roman(spoken) and 75 <= wc <= 135:
            break
        prompt += (f"\n\nYour previous draft had {wc} words"
                   f"{' and contained non-Latin script' if has_non_roman(spoken) else ''}. Rewrite to 80-125 words, Roman Urdu only.")
    d = out.model_dump()
    d["spoken_full"] = " ".join(sc.spoken for sc in out.scenes)
    d["word_count"] = word_count(d["spoken_full"])
    d["estimated_duration_s"] = round(d["word_count"] / 2.6, 1)
    d["subtitle_transcript"] = [sc.spoken for sc in out.scenes]
    with SessionLocal() as s:
        row = Script(project_id=project_id, idea_id=(idea or {}).get("id"), title=out.title, data=d, source="claude")
        s.add(row)
        s.commit()
        return row.id


def manual_script(title, text, project_id=None):
    sentences = [x.strip() for x in re.split(r"(?<=[.?!])\s+", text.strip()) if x.strip()]
    d = {"title": title, "spoken_full": text.strip(), "scenes": [
        {"start_s": 0, "end_s": 0, "purpose": "value", "spoken": s_, "broll_queries": [], "visual_direction": "", "sfx": ""}
        for s_ in sentences], "hook_variations": [], "cta": "", "cta_keyword": "", "hook_title": "", "hook_subtitle": "",
        "keywords": [], "fact_check_notes": [], "subtitle_transcript": sentences}
    d["word_count"] = word_count(text)
    d["estimated_duration_s"] = round(d["word_count"] / 2.6, 1)
    with SessionLocal() as s:
        row = Script(project_id=project_id, title=title, data=d, source="manual")
        s.add(row)
        s.commit()
        return row.id
