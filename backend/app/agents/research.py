"""Research Agent + Content Strategist.

Data comes only from official APIs (YouTube Data API v3, Instagram Graph API) and user-entered
competitors. Metrics from APIs are labelled 'verified'; Claude's judgement scores are 'estimated';
anything we cannot measure is 'unavailable'. Nothing is invented.
"""
import math
from datetime import datetime, timezone

from ..db import SessionLocal, ResearchRun, Competitor
from ..providers import youtube, claude
from ..util import StageError
from .schemas import OpportunityList

CATEGORY_QUERIES = {
    "Amazon": ["amazon fba urdu", "amazon fba hindi", "amazon private label", "amazon fbm", "amazon ppc tips",
               "amazon product listing optimization"],
    "Shopify": ["shopify dropshipping", "shopify store tips", "dropshipping winning product"],
    "China Sourcing": ["china sourcing yiwu market", "guangzhou wholesale market", "alibaba supplier tips",
                       "1688 sourcing", "china factory product sourcing"],
    "AI Automation": ["ai ecommerce automation", "ai tools amazon sellers", "chatgpt amazon listing"],
    "Product Hunting": ["amazon product research", "winning product hunting", "product research amazon fba"],
    "E-commerce News": ["amazon seller news", "ecommerce news 2026"],
    "Business Case Studies": ["amazon fba case study", "ecommerce success story"],
    "Tutorials": ["amazon seller central tutorial", "how to start amazon fba"],
}
NICHE_WORDS = {"amazon", "fba", "fbm", "shopify", "dropshipping", "alibaba", "yiwu", "guangzhou", "china", "sourcing",
               "wholesale", "private", "label", "ppc", "listing", "product", "ecommerce", "e-commerce", "seller",
               "supplier", "factory", "brand", "1688", "ai", "automation", "shipping"}


def _iso_age_days(ts):
    try:
        d = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return max(0.5, (datetime.now(timezone.utc) - d).total_seconds() / 86400)
    except Exception:
        return None


def _metrics(v):
    age = _iso_age_days(v.get("published_at") or "")
    views, likes, comments = v.get("views"), v.get("likes"), v.get("comments")
    v["age_days"] = round(age, 1) if age else None
    v["views_per_day"] = round(views / age, 1) if views is not None and age else None
    v["engagement_rate"] = (round(((likes or 0) + (comments or 0)) / views * 100, 2) if views else None)
    words = set((v.get("title", "") + " " + " ".join(v.get("tags", []))).lower().replace("#", " ").split())
    v["niche_relevance"] = round(min(1.0, len(words & NICHE_WORDS) / 3), 2)
    return v


def _deterministic_rank(videos, limit=20):
    def score(v):
        s = 0
        if v.get("views"):
            s += math.log10(v["views"] + 1) * 2
        if v.get("views_per_day"):
            s += math.log10(v["views_per_day"] + 1) * 3
        if v.get("engagement_rate"):
            s += min(v["engagement_rate"], 15) / 3
        s += v.get("niche_relevance", 0) * 4
        return s
    ranked = sorted(videos, key=score, reverse=True)[:limit]
    out = []
    for v in ranked:
        out.append({
            "title": v["title"], "topic": v["title"], "category": "", "why_now": "",
            "proven_hook": v["title"], "format": "short-form video", "content_gap": "",
            "source_urls": [v["url"]],
            "scores": {"audience_interest": {"value": v.get("views"), "label": "verified", "unit": "views"},
                       "recent_popularity": {"value": v.get("views_per_day"), "label": "verified", "unit": "views/day"},
                       "engagement_signals": {"value": v.get("engagement_rate"), "label": "verified", "unit": "% (likes+comments)/views"},
                       "search_demand": {"value": None, "label": "unavailable"},
                       "content_originality": {"value": None, "label": "unavailable"},
                       "educational_value": {"value": None, "label": "unavailable"},
                       "audience_relevance": {"value": v.get("niche_relevance"), "label": "estimated", "unit": "keyword match 0-1"}},
            "ranking_method": "deterministic (Claude not configured)",
        })
    return out


STRATEGIST_SYSTEM = """You are the Content Strategist for an e-commerce education creator who makes 30-50 second
Roman Urdu short videos (audience: Pakistani/Indian/Gulf e-commerce beginners and sellers targeting Amazon
Saudi Arabia, UAE, USA, UK, Canada, Australia, Japan; Shopify; China sourcing).
You receive REAL video data from the YouTube Data API. Rank the strongest video opportunities.
Rules:
- Use only the videos provided. Every opportunity's source_urls must be copied exactly from the provided urls.
- Never invent numbers. Your 0-10 scores are your judgement and will be labelled 'estimated'.
- Prefer topics this creator can teach credibly (Amazon FBA/FBM, private label, China sourcing, product hunting,
  AI for e-commerce). Avoid get-rich-quick claims.
- audience_questions, trending_subjects and hook_patterns must be derived from the provided titles/descriptions."""


def run(run_id, log=print):
    with SessionLocal() as s:
        rr = s.get(ResearchRun, run_id)
        rr.status = "running"
        s.commit()
        query, cats, markets = rr.query, rr.categories or [], rr.markets or []
    try:
        if not youtube.configured():
            raise StageError("Viral research needs the YouTube Data API key (Integrations). No results were generated.")
        queries = [query] if query else []
        for c in cats or ["Amazon", "China Sourcing", "Product Hunting"]:
            queries += CATEGORY_QUERIES.get(c, [])[:2]
        queries = list(dict.fromkeys(q for q in queries if q))[:8]
        regions = (markets or [None])[:2]
        ids = []
        for q in queries:
            for r in regions:
                log(f"YouTube search: '{q}' region={r}")
                ids += youtube.search_videos(q, region=r, max_results=25)
        ids = list(dict.fromkeys(ids))
        videos = [_metrics(v) for v in youtube.video_details(ids)]
        videos = [v for v in videos if v.get("niche_relevance", 0) > 0]
        ch_ids = list(dict.fromkeys(v["channel_id"] for v in videos if v.get("channel_id")))
        channels = {c["id"]: c for c in youtube.channel_details(ch_ids)}

        # competitors = channels that keep producing high-performing niche content
        by_ch = {}
        for v in videos:
            by_ch.setdefault(v["channel_id"], []).append(v)
        comp = []
        for cid, vids in by_ch.items():
            ch = channels.get(cid)
            if not ch:
                continue
            vids.sort(key=lambda x: x.get("views") or 0, reverse=True)
            comp.append({**ch, "found_videos": len(vids), "found_views": sum(v.get("views") or 0 for v in vids),
                         "top_videos": vids[:5]})
        comp.sort(key=lambda c: (c["found_views"], c.get("followers") or 0), reverse=True)
        comp = comp[:15]

        if claude.configured():
            compact = [{k: v.get(k) for k in ("url", "title", "channel", "published_at", "views", "likes", "comments",
                                               "views_per_day", "engagement_rate", "description")} for v in
                       sorted(videos, key=lambda x: x.get("views_per_day") or 0, reverse=True)[:80]]
            import json
            res = claude.structured(STRATEGIST_SYSTEM,
                                    f"Return the 20 strongest opportunities.\nVIDEOS JSON:\n{json.dumps(compact, ensure_ascii=False)}",
                                    OpportunityList, purpose="strategist")
            valid = {v["url"] for v in videos}
            opps = []
            for o in res.opportunities[:20]:
                d = o.model_dump()
                d["source_urls"] = [u for u in d["source_urls"] if u in valid]
                if not d["source_urls"]:
                    continue
                src = [v for v in videos if v["url"] in d["source_urls"]]
                d["verified_metrics"] = [{"url": v["url"], "views": v.get("views"), "likes": v.get("likes"),
                                          "comments": v.get("comments"), "published_at": v.get("published_at"),
                                          "views_per_day": v.get("views_per_day")} for v in src]
                d["scores"] = {k: {"value": val, "label": "estimated", "unit": "0-10 (Claude judgement)"}
                               for k, val in d["scores"].items()}
                d["ranking_method"] = "Claude strategist over verified YouTube metrics"
                opps.append(d)
            insights = {"audience_questions": res.audience_questions, "trending_subjects": res.trending_subjects,
                        "hook_patterns": res.hook_patterns, "label": "estimated (Claude analysis of verified titles)"}
        else:
            opps = _deterministic_rank(videos)
            insights = {"audience_questions": [], "trending_subjects": [], "hook_patterns": [],
                        "label": "unavailable (configure Claude for qualitative insights)"}

        result = {"queries": queries, "regions": regions, "video_count": len(videos),
                  "videos": sorted(videos, key=lambda x: x.get("views") or 0, reverse=True)[:150],
                  "competitors": [{k: c[k] for k in c if k != "top_videos"} | {"top_videos": [
                      {k: v.get(k) for k in ("url", "title", "views", "likes", "comments", "published_at")} for v in c["top_videos"]]}
                      for c in comp],
                  "opportunities": opps, "insights": insights,
                  "notes": ["YouTube metrics are verified API values at research time.",
                            "TikTok: the official Research API is restricted to approved researchers, so TikTok accounts must be added manually.",
                            "Instagram: add accounts by username in Competitor Intelligence once the Graph API is configured."]}
        with SessionLocal() as s:
            for c in comp:
                if not s.query(Competitor).filter_by(platform="YouTube", external_id=c["id"]).first():
                    s.add(Competitor(platform="YouTube", name=c["name"], url=c["url"], external_id=c["id"],
                                     followers=c.get("followers"), source="youtube_api", verification="verified",
                                     research_run_id=run_id, data={k: c[k] for k in c if k != "top_videos"} | {
                                         "top_videos": result["competitors"][comp.index(c)]["top_videos"]}))
            rr = s.get(ResearchRun, run_id)
            rr.result, rr.status = result, "done"
            s.commit()
        return result
    except Exception as e:
        with SessionLocal() as s:
            rr = s.get(ResearchRun, run_id)
            rr.status, rr.error = "failed", str(e)
            s.commit()
        raise
