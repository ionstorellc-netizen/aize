"""Edit Decision List: the single source of truth that the editor agent writes, the timeline UI edits,
and the renderer turns into an MP4. Everything that sits on spoken words is anchored to SOURCE time
(src_t), so cutting/trimming/reordering shots keeps overlays and subtitles locked to the words.
"""
import re
import uuid

NICHE_TERMS = [
    "amazon fba", "amazon fbm", "fba", "fbm", "private label", "brand launch", "shopify", "dropshipping",
    "automation", "ai", "product hunting", "winning product", "alibaba", "1688", "yiwu", "guangzhou",
    "china", "sourcing", "wholesale", "factory", "manufacturer", "packaging", "branding", "ppc", "listing",
    "shipping", "mentorship", "training", "course", "video courses", "seller central", "profit", "supplier",
    "business", "e-commerce", "ecommerce", "inventory", "warehouse",
]


def _id():
    return uuid.uuid4().hex[:8]


def _norm(w):
    return re.sub(r"[^\w']", "", w.lower())


# ------------------------------------------------------------------ cleanup passes

def remove_stutters(words):
    """Drop the first copy of immediately repeated 2-6 word runs ("ke upar business start, ke upar business start")."""
    keep = [True] * len(words)
    n = [_norm(w["w"]) for w in words]
    i = 0
    while i < len(words):
        hit = False
        for k in range(6, 1, -1):
            if i + 2 * k <= len(words) and n[i:i + k] == n[i + k:i + 2 * k] and all(n[i:i + k]):
                for j in range(i, i + k):
                    keep[j] = False
                i += k
                hit = True
                break
        if not hit:
            i += 1
    return [w for w, k in zip(words, keep) if k]


def sentences(words):
    """Group words into sentences using punctuation and pauses."""
    out, cur = [], []
    for i, w in enumerate(words):
        cur.append(w)
        nxt = words[i + 1] if i + 1 < len(words) else None
        gap = (nxt["s"] - w["e"]) if nxt else 1
        if re.search(r"[.?!]$", w["w"]) or gap > 0.6 or (len(cur) >= 18 and re.search(r",$", w["w"])):
            out.append(cur)
            cur = []
    if cur:
        out.append(cur)
    return [{"id": i, "words": s, "s": s[0]["s"], "e": s[-1]["e"], "text": " ".join(x["w"] for x in s)}
            for i, s in enumerate(out)]


def trim_redundant(sents, max_s, keep_ids=None):
    """Bring the talk under max_s seconds by dropping the most repetitive sentences (never the first or last two)."""
    if keep_ids is not None:
        return [s for s in sents if s["id"] in set(keep_ids)]
    total = lambda ss: sum(s["e"] - s["s"] + 0.1 for s in ss)
    cur = list(sents)
    if total(cur) <= max_s:
        return cur
    stop = {"hai", "hain", "ke", "ki", "ka", "ko", "se", "me", "mein", "aur", "to", "toh", "jo", "the", "a", "and",
            "you", "will", "kar", "karna", "karne", "is", "it", "be", "ek", "yeh", "ye", "woh", "wo", "bhi", "nahi"}
    while total(cur) > max_s and len(cur) > 4:
        seen, scores = set(), []
        for idx, s in enumerate(cur):
            toks = {_norm(w["w"]) for w in s["words"]} - stop - {""}
            overlap = len(toks & seen) / max(1, len(toks))
            seen |= toks
            if 0 < idx < len(cur) - 2:
                scores.append((overlap, -(s["e"] - s["s"]), idx))
        if not scores:
            break
        scores.sort(reverse=True)
        cur.pop(scores[0][2])
    return cur


# ------------------------------------------------------------------ build

def build(transcript, style, source_path, script=None, broll_plan=None, cta=None, max_duration=50.0,
          keep_sentence_ids=None, hook=None):
    pace = style["pacing"]
    words = remove_stutters(transcript["words"])
    sents = sentences(words)
    kept = trim_redundant(sents, max_duration - 0.5, keep_sentence_ids)
    kept_words = [w for s in kept for w in s["words"]]

    # 1) speech islands -> jump cuts
    islands, cur = [], [kept_words[0]] if kept_words else []
    for a, b in zip(kept_words, kept_words[1:]):
        if b["s"] - a["e"] > pace["remove_pauses_longer_than"] or b["s"] < a["e"] - 0.01:
            islands.append(cur)
            cur = []
        cur.append(b)
    if cur:
        islands.append(cur)
    pad = pace["keep_padding"]

    # 2) split islands into shots of 3..6 s on word boundaries, assign framing pattern
    lo, hi = pace["angle_change_every_s"]
    framings = {f["name"]: f["zoom"] for f in style["camera"]["framings"]}
    pattern = style["camera"]["framing_pattern"]
    segments, k = [], 0
    for isl in islands:
        start_i = 0
        while start_i < len(isl):
            j = start_i
            while j + 1 < len(isl) and isl[j + 1]["e"] - isl[start_i]["s"] < hi:
                j += 1
                if isl[j]["e"] - isl[start_i]["s"] >= lo and re.search(r"[,.?!]$", isl[j]["w"]):
                    break
            src_in = max(0.0, isl[start_i]["s"] - (pad if start_i == 0 else 0.0))
            src_out = isl[j]["e"] + (pad if j == len(isl) - 1 else 0.0)
            if j + 1 < len(isl):  # inner split: cut exactly between words
                mid = (isl[j]["e"] + isl[j + 1]["s"]) / 2
                src_out = mid
            if start_i > 0:
                src_in = segments[-1]["src_out"]
            name = pattern[k % len(pattern)]
            segments.append({"id": _id(), "src_in": round(src_in, 3), "src_out": round(src_out, 3),
                             "framing": name, "zoom": framings[name], "push": True, "transition": "cut"})
            k += 1
            start_i = j + 1
    # avoid overlaps between consecutive islands
    for a, b in zip(segments, segments[1:]):
        if b["src_in"] < a["src_out"]:
            m = round((a["src_out"] + b["src_in"]) / 2, 3)
            a["src_out"], b["src_in"] = m, m

    edl = {"version": 1, "canvas": style["canvas"], "source": str(source_path), "segments": segments,
           "broll": [], "titles": [], "subtitles": [], "sfx": [], "cta": None,
           "audio": {"music": "generated_pad", "music_path": None, "music_db": style["audio"]["music_db"],
                     "sfx_db": style["audio"]["sfx_db"], "voice_lufs": style["audio"]["voice_target_lufs"],
                     "voice_tp": style["audio"]["voice_true_peak_db"], "duck": style["audio"]["duck_music_during_speech"]},
           "grade": dict(style["grade"]), "style_name": style.get("name"), "dropped_sentences":
               [s["text"] for s in sents if s not in kept]}
    total = timeline_duration(edl)

    # 3) subtitles (phrase chunks), anchored to source time
    sub = style["subtitles"]
    phrases, cur = [], []
    for i, w in enumerate(kept_words):
        cur.append(w)
        nxt = kept_words[i + 1] if i + 1 < len(kept_words) else None
        text_len = len(" ".join(x["w"] for x in cur))
        brk = (len(cur) >= sub["max_words_per_line"] or text_len >= sub["max_chars_per_line"]
               or re.search(r"[,.?!]$", w["w"]) or nxt is None or nxt["s"] - w["e"] > 0.45)
        if brk:
            phrases.append(cur)
            cur = []
    for ph in phrases:
        edl["subtitles"].append({"id": _id(), "words": [{"w": x["w"], "s": x["s"], "e": x["e"]} for x in ph]})

    # 4) hook title on first shot
    tstyle = style["titles"]
    first_src = segments[0]["src_in"] if segments else 0
    hook_text = (hook or {}).get("text") or " ".join(w["w"] for w in kept_words[:4]).strip(",.?!")
    hook_sub = (hook or {}).get("sub", "")
    edl["titles"].append({"id": _id(), "kind": "hook", "src_t": first_src, "dur": tstyle["duration_s"],
                          "text": hook_text, "sub": hook_sub})
    edl["sfx"].append({"id": _id(), "src_t": first_src, "kind": "impact"})

    # 5) overlays schedule: keyword callouts + B-roll, never overlapping each other
    busy = [(0.0, tstyle["duration_s"] + 0.3)]
    cta_len = style["cta"]["duration_s"]
    cta_start = max(0, total - cta_len)

    def free(t0, t1):
        return t1 <= cta_start - 0.2 and all(t1 <= a or t0 >= b for a, b in busy)

    tmap = make_src_to_tl(edl)
    # B-roll first (it is the priority visual layer)
    gap_lo, gap_hi = style["broll"]["gap_s"]
    for i, item in enumerate(broll_plan or []):
        t0 = tmap(item["src_t"])
        if t0 is None:
            continue
        dur = max(style["broll"]["min_len_s"], min(style["broll"]["max_len_s"], item.get("dur", 2.2)))
        if not free(t0 - gap_lo * 0.5, t0 + dur):
            continue
        busy.append((t0, t0 + dur))
        edl["broll"].append({"id": _id(), "src_t": item["src_t"], "dur": round(dur, 2), "path": item["path"],
                             "media": item.get("media", "video"), "mode": item.get("mode", "card"),
                             "label": item.get("label", ""), "query": item.get("query", ""),
                             "asset_id": item.get("asset_id"), "source": item.get("source", ""),
                             "in": item.get("in", 0.0)})
        edl["sfx"].append({"id": _id(), "src_t": item["src_t"], "kind": "whoosh" if item.get("mode") == "full" else "pop"})

    # keyword callouts at first mention of niche terms / script keywords
    kw_list = [k.lower() for k in ((script or {}).get("keywords") or [])] or NICHE_TERMS
    used = set()
    lowered = [_norm(w["w"]) for w in kept_words]
    for idx, w in enumerate(kept_words):
        for term in kw_list:
            parts = term.split()
            if lowered[idx:idx + len(parts)] == [_norm(p) for p in parts] and term not in used:
                t0 = tmap(w["s"])
                if t0 is None or not free(t0, t0 + 1.4):
                    continue
                used.add(term)
                busy.append((t0, t0 + 1.4))
                label = " ".join(x["w"] for x in kept_words[idx:idx + len(parts)]).strip(",.?!")
                edl["titles"].append({"id": _id(), "kind": "keyword", "src_t": w["s"], "dur": 1.4,
                                      "text": label, "sub": ""})
                edl["sfx"].append({"id": _id(), "src_t": w["s"], "kind": "click"})
                break
        if len(used) >= 6:
            break

    # 6) CTA over the last seconds
    c = cta or {}
    edl["cta"] = {"text": c.get("text") or "Comment \"MENTOR\" and I'll send you the details",
                  "sub": c.get("sub") or "MENTOR", "dur": cta_len, "fade": style["cta"]["end_fade_s"]}
    return edl


# ------------------------------------------------------------------ time mapping

def timeline_duration(edl):
    return round(sum(s["src_out"] - s["src_in"] for s in edl["segments"]), 3)


def make_src_to_tl(edl):
    spans, t = [], 0.0
    for s in edl["segments"]:
        spans.append((s["src_in"], s["src_out"], t))
        t += s["src_out"] - s["src_in"]

    def f(src_t):
        for a, b, off in spans:
            if a - 1e-3 <= src_t < b:
                return round(off + (src_t - a), 3)
        return None
    return f


def resolved(edl):
    """Timeline-time view used by the renderer and the UI."""
    f = make_src_to_tl(edl)
    total = timeline_duration(edl)
    out = {"duration": total, "segments": [], "broll": [], "titles": [], "subtitles": [], "sfx": []}
    t = 0.0
    for s in edl["segments"]:
        d = s["src_out"] - s["src_in"]
        out["segments"].append({**s, "t": round(t, 3), "dur": round(d, 3)})
        t += d
    for key in ("broll", "titles", "sfx"):
        for o in edl.get(key, []):
            tt = f(o["src_t"])
            if tt is not None:
                out[key].append({**o, "t": tt})
    for ph in edl.get("subtitles", []):
        ws = []
        for w in ph["words"]:
            a = f(w["s"])
            if a is None:
                continue
            b = f(max(w["s"], w["e"] - 0.01))
            ws.append({"w": w["w"], "t0": a, "t1": (b + 0.01) if b is not None else a + (w["e"] - w["s"])})
        if ws:
            out["subtitles"].append({"id": ph["id"], "t0": ws[0]["t0"], "t1": ws[-1]["t1"], "words": ws})
    # make phrases continuous until the next one starts (no flicker), but cap holds
    subs = out["subtitles"]
    for a, b in zip(subs, subs[1:]):
        if 0 < b["t0"] - a["t1"] < 0.6:
            a["t1"] = b["t0"]
    if edl.get("cta"):
        c = edl["cta"]
        out["cta"] = {**c, "t": max(0.0, total - c["dur"])}
    return out
