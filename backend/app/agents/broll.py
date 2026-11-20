"""B-roll Intelligence Agent: one visual decision per spoken sentence.

Source priority (configurable): your uploaded library -> free stock (Pexels, else Pixabay) -> typographic graphic.
Graphics are clearly designed cards (headline text on the brand colour); the agent never fabricates
screenshots, dashboards, results or statistics.
"""
import json
import re
from pathlib import Path

from ..db import SessionLocal, Asset
from ..providers import stock, claude
from ..engine import graphics
from ..engine.edl import sentences, remove_stutters
from ..util import probe
from .schemas import BrollPlan

LEXICON = [
    (("amazon", "fba", "seller", "listing"), ["amazon warehouse boxes", "online shopping delivery package", "laptop ecommerce dashboard"]),
    (("fbm",), ["packing shipping boxes home office", "shipping label printer"]),
    (("china", "chinese", "yiwu", "guangzhou", "wholesale", "market"), ["china wholesale market", "asian market stalls products", "warehouse shelves products"]),
    (("factory", "manufacturer", "manufacturing", "production"), ["factory production line", "manufacturing workers assembly"]),
    (("alibaba", "supplier", "sourcing", "1688"), ["business video call supplier", "product samples inspection"]),
    (("shipping", "container", "freight"), ["shipping containers port", "cargo ship"]),
    (("packaging", "branding", "brand", "label"), ["product packaging design", "branded boxes packaging"]),
    (("shopify", "dropshipping", "store"), ["online store laptop shopping", "ecommerce website on phone"]),
    (("ai", "automation", "chatgpt", "tools"), ["artificial intelligence computer screen", "automation workflow technology"]),
    (("ppc", "ads", "marketing"), ["digital marketing analytics screen", "advertising on smartphone"]),
    (("profit", "money", "paisa", "income", "loss"), ["counting money", "business finance calculator"]),
    (("training", "mentorship", "mentor", "learn", "seekhna", "course", "courses", "student"), ["mentor teaching student laptop", "business coaching session", "online course laptop learning"]),
    (("problem", "mistake", "galti"), ["frustrated man laptop", "stressed entrepreneur"]),
    (("business", "start"), ["entrepreneur working laptop", "small business owner"]),
    (("product", "products", "hunting", "research"), ["product research laptop", "products on shelf"]),
]

SYSTEM = """You are the B-roll Intelligence Agent for short e-commerce education videos (Roman Urdu speech).
For each numbered sentence, give 2 concrete English stock-footage queries that literally depict what is said
(prefer real-world footage: warehouses, markets in China, factories, packaging, laptops with stores, shipping).
Set prefer_graphic=true only when the sentence is abstract (an opinion/claim) and a typographic card fits better;
then label is a 2-4 word headline taken from the sentence. Never suggest fake dashboards or fake statistics."""


def _lexicon_queries(text):
    t = set(re.findall(r"[a-z0-9]+", text.lower()))
    for keys, qs in LEXICON:
        if t & set(keys):
            return qs
    return []


STRONG = {"amazon": "Amazon", "fba": "Amazon FBA", "fbm": "Amazon FBM", "shopify": "Shopify", "dropshipping": "Dropshipping",
          "china": "China sourcing", "yiwu": "Yiwu market", "guangzhou": "Guangzhou", "alibaba": "Alibaba", "1688": "1688",
          "factory": "Factory", "supplier": "Suppliers", "ppc": "Amazon PPC", "listing": "Listing", "packaging": "Packaging",
          "mentorship": "Live mentorship", "mentor": "Mentor", "training": "Live training", "course": "Video courses",
          "courses": "Video courses", "shipping": "Shipping", "profit": "Profit", "ai": "AI tools", "automation": "Automation",
          "e-commerce": "E-commerce", "ecommerce": "E-commerce", "wholesale": "Wholesale", "private": "Private label"}


def _key_phrase(sent):
    """Headline for a typographic card when Claude is not configured: the niche term the sentence is about."""
    for w in sent["words"]:
        t = re.sub(r"[^\w-]", "", w["w"].lower())
        if t in STRONG:
            return STRONG[t]
    return None


def _library_match(queries, used, s):
    words = set(" ".join(queries).lower().split())
    best, score = None, 0
    for a in s.query(Asset).filter(Asset.kind.in_(["broll", "image"])).all():
        if a.id in used:
            continue
        sc = len(words & {t.lower() for t in (a.tags or [])} | (words & set(a.name.lower().split())))
        if sc > score:
            best, score = a, sc
    return best if score >= 1 else None


def plan(transcript, workdir: Path, style, script=None, project_id=None, log=print):
    prefs_sources = ["library", "pexels", "generated"]
    words = remove_stutters(transcript["words"])
    sents = sentences(words)
    picks = {}
    if claude.configured():
        numbered = [{"id": s["id"], "text": s["text"]} for s in sents]
        extra = ""
        if script:
            extra = "\nScript scene suggestions:\n" + json.dumps([{"spoken": sc["spoken"], "broll_queries": sc["broll_queries"]}
                                                                  for sc in script.get("scenes", [])], ensure_ascii=False)
        res = claude.structured(SYSTEM, f"SENTENCES:\n{json.dumps(numbered, ensure_ascii=False)}{extra}", BrollPlan,
                                project_id=project_id, purpose="broll")
        picks = {p.sentence_id: p.model_dump() for p in res.picks}
    bdir = workdir / "broll"
    bdir.mkdir(exist_ok=True)
    used_assets, used_pexels, plan_items, used_labels = set(), set(), [], set()
    card_ratio = style["broll"]["card_ratio"]
    n_full = 0
    with SessionLocal() as s:
        for idx, sent in enumerate(sents):
            if idx == 0:
                continue  # the hook shot stays on the presenter
            p = picks.get(sent["id"])
            if p is None:
                label = _key_phrase(sent)
                if picks or not _lexicon_queries(sent["text"]) or not label:
                    continue  # nothing concrete to show for this sentence: stay on the presenter
                p = {"queries": _lexicon_queries(sent["text"]), "label": label, "prefer_graphic": False}
            queries = p["queries"] or _lexicon_queries(sent["text"])
            anchor = sent["words"][min(1, len(sent["words"]) - 1)]["s"]
            dur = min(3.0, max(1.6, (sent["e"] - sent["s"]) * 0.7))
            item = None
            if not p.get("prefer_graphic"):
                if "library" in prefs_sources and queries:
                    a = _library_match(queries, used_assets, s)
                    if a:
                        used_assets.add(a.id)
                        item = {"path": a.path, "media": "image" if a.kind == "image" else "video", "asset_id": a.id,
                                "source": "library", "query": " / ".join(queries), "label": a.name}
                if not item and "pexels" in prefs_sources and stock.configured() and queries:
                    for q in queries:
                        try:
                            found = [r for r in stock.search(q) if f"{r['provider']}_{r['id']}" not in used_pexels]
                        except Exception as e:
                            log(f"Stock search failed for '{q}': {e}")
                            found = []
                        if found:
                            r = found[0]
                            used_pexels.add(f"{r['provider']}_{r['id']}")
                            dest = bdir / f"{r['provider']}_{r['id']}.mp4"
                            if not dest.exists():
                                stock.download(r, dest)
                            info = probe(dest)
                            a = Asset(kind="broll", path=str(dest), name=q, tags=q.split(), source=r["provider"],
                                      license=r["license"] + (f" — by {r['author']}" if r.get("author") else ""),
                                      source_url=r["url"], duration=info["duration"],
                                      width=(info["video"] or {}).get("width"), height=(info["video"] or {}).get("height"),
                                      project_id=project_id)
                            # Commit in its own short session: holding a write transaction open across the
                            # next network searches/downloads locked SQLite for the job log and event writers.
                            with SessionLocal() as ws:
                                ws.add(a)
                                ws.commit()
                            used_assets.add(a.id)  # never reuse this clip as a 'library' match later
                            item = {"path": str(dest), "media": "video", "asset_id": a.id, "source": r["provider"],
                                    "query": q, "label": q, "in": min(1.0, max(0, (info["duration"] or 3) - dur - 0.2))}
                            break
            if not item:
                label = p.get("label") or " ".join(w["w"] for w in sent["words"][:5]).strip(",.?!")
                if label.lower() in used_labels:
                    continue  # never show the same graphic twice
                used_labels.add(label.lower())
                png = bdir / f"graphic_{sent['id']}.jpg"
                graphics.graphic_card(label, "", style, png)
                item = {"path": str(png), "media": "image", "source": "generated", "query": "",
                        "label": label, "asset_id": None}
            want_full = item["media"] == "video" and (n_full + 1) / (len(plan_items) + 1) <= (1 - card_ratio)
            item["mode"] = "full" if want_full else "card"
            n_full += 1 if want_full else 0
            item.update({"src_t": anchor, "dur": round(dur, 2), "sentence": sent["text"]})
            plan_items.append(item)
        s.commit()
    log(f"B-roll plan: {len(plan_items)} picks "
        f"({sum(1 for i in plan_items if i['source']=='pexels')} Pexels, "
        f"{sum(1 for i in plan_items if i['source']=='pixabay')} Pixabay, "
        f"{sum(1 for i in plan_items if i['source']=='library')} library, "
        f"{sum(1 for i in plan_items if i['source']=='generated')} graphics)")
    return plan_items
