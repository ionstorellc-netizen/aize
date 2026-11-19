"""PNG overlays (titles, keyword bars, CTA, B-roll cards, typographic graphics) drawn with Pillow."""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageFilter

from ..config import FONTS_DIR
from ..util import hex_to_rgb

FONT_FILES = {
    "Playfair Display SemiBold": "PlayfairDisplay-SemiBold.ttf",
    "Playfair Display Italic": "PlayfairDisplay-MediumItalic.ttf",
    "Inter Black": "Inter-Black.ttf",
    "Inter ExtraBold": "Inter-ExtraBold.ttf",
    "Inter Medium": "Inter-Medium.ttf",
    "Instrument Serif": "InstrumentSerif-Regular.ttf",
    "Instrument Serif Italic": "InstrumentSerif-Italic.ttf",
}


def font(name, size):
    return ImageFont.truetype(str(FONTS_DIR / FONT_FILES.get(name, "Inter-Black.ttf")), size)


def _rgba(h, a=255):
    return (*hex_to_rgb(h), a)


def _fit(draw, text, fname, size, max_w):
    while size > 20:
        f = font(fname, size)
        if draw.textlength(text, font=f) <= max_w:
            return f
        size -= 4
    return font(fname, size)


def _shadow(img, radius=14, opacity=110):
    a = img.split()[-1].filter(ImageFilter.GaussianBlur(radius))
    sh = Image.new("RGBA", img.size, (0, 0, 0, 0))
    sh.putalpha(a.point(lambda v: v * opacity // 255))
    out = Image.new("RGBA", img.size, (0, 0, 0, 0))
    out.alpha_composite(sh, (0, 8))
    out.alpha_composite(img)
    return out


def hook_title(text, sub, style, out: Path, W=1080):
    """Giant editorial serif headline (+ optional gold italic line), transparent PNG."""
    pal, tc = style["palette"], style["titles"]
    img = Image.new("RGBA", (W, 760), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    words = text.upper().split()
    size = tc["hook_font_size"]
    while True:  # shrink until the whole headline fits in 3 lines
        probe = font("Instrument Serif", size)
        lines, cur = [], ""
        for w in words:
            t = (cur + " " + w).strip()
            if d.textlength(t, font=probe) > W - 110 and cur:
                lines.append(cur)
                cur = w
            else:
                cur = t
        if cur:
            lines.append(cur)
        if len(lines) <= 3 or size <= 90:
            break
        size -= 12
    lines = lines[:3]
    tc = {**tc, "hook_font_size": size}
    y = 30
    for ln in lines:
        f = _fit(d, ln, "Instrument Serif", tc["hook_font_size"], W - 100)
        w = d.textlength(ln, font=f)
        d.text(((W - w) / 2, y), ln, font=f, fill=_rgba(pal["cream"]))
        y += int(f.size * 0.92)
    if sub:
        f = _fit(d, sub, "Instrument Serif Italic", int(tc["hook_font_size"] * 0.55), W - 140)
        w = d.textlength(sub, font=f)
        d.text(((W - w) / 2, y + 8), sub, font=f, fill=_rgba(pal["gold"]))
        y += f.size + 20
    img = img.crop((0, 0, W, min(760, y + 40)))
    _shadow(img, 18, 150).save(out)
    return out


def keyword_bar(text, sub, style, out: Path, W=1080):
    """BIG SANS word on forest-green bar, optional serif italic line under it (reference 'BIGGER / captions.')."""
    pal, tc = style["palette"], style["titles"]
    img = Image.new("RGBA", (W, 420), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    f = _fit(d, text.upper(), "Inter Black", tc["keyword_font_size"], W - 200)
    tw = d.textlength(text.upper(), font=f)
    bx0, by0 = (W - tw) / 2 - 34, 20
    bx1, by1 = (W + tw) / 2 + 34, 20 + f.size + 46
    d.rectangle((bx0, by0, bx1, by1), fill=_rgba(pal["primary"], 240))
    d.text(((W - tw) / 2, by0 + 14), text.upper(), font=f, fill=_rgba(pal["cream"]))
    y = by1
    if sub:
        fs = _fit(d, sub, "Instrument Serif Italic", int(tc["keyword_font_size"] * 0.85), W - 160)
        sw = d.textlength(sub, font=fs)
        d.rectangle(((W - sw) / 2 - 26, y, (W + sw) / 2 + 26, y + fs.size + 30), fill=_rgba(pal["primary"], 240))
        d.text(((W - sw) / 2, y + 6), sub, font=fs, fill=_rgba(pal["gold"]))
        y += fs.size + 30
    img = img.crop((0, 0, W, int(y) + 20))
    _shadow(img, 12, 120).save(out)
    return out


def cta_card(text, sub, style, out: Path, W=1080):
    """White rounded box at top with bold dark text + comment-style bubble (reference CTA)."""
    pal = style["palette"]
    img = Image.new("RGBA", (W, 420), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    f = font("Inter ExtraBold", 54)
    lines, cur = [], ""
    for w in text.split():
        t = (cur + " " + w).strip()
        if d.textlength(t, font=f) > W - 260 and cur:
            lines.append(cur)
            cur = w
        else:
            cur = t
    lines.append(cur)
    h = 40 + len(lines) * 66 + 30
    tw = max(d.textlength(l, font=f) for l in lines)
    x0 = (W - tw) / 2 - 40
    d.rounded_rectangle((x0, 10, W - x0, 10 + h), radius=28, fill=(255, 255, 255, 250))
    y = 10 + 34
    for l in lines:
        lw = d.textlength(l, font=f)
        d.text(((W - lw) / 2, y), l, font=f, fill=_rgba("#111111"))
        y += 66
    if sub:
        fb = font("Inter Medium", 40)
        bw = d.textlength(sub, font=fb) + 120
        bx = (W - bw) / 2
        by = 10 + h + 22
        d.rounded_rectangle((bx, by, bx + bw, by + 80), radius=40, fill=(255, 255, 255, 245))
        d.ellipse((bx + 16, by + 14, bx + 68, by + 66), fill=_rgba(pal["primary"]))
        d.text((bx + 88, by + 16), sub, font=fb, fill=_rgba("#111111"))
        y = by + 90
    img = img.crop((0, 0, W, int(y) + 20))
    _shadow(img, 14, 120).save(out)
    return out


def card_mask(w, h, radius, out: Path):
    m = Image.new("L", (w, h), 0)
    ImageDraw.Draw(m).rounded_rectangle((0, 0, w - 1, h - 1), radius=radius, fill=255)
    m.save(out)
    return out


def card_frame(w, h, radius, border, color, out: Path):
    """Border + drop shadow PNG drawn around a B-roll card (card content is composited inside)."""
    pad = 40
    img = Image.new("RGBA", (w + pad * 2, h + pad * 2), (0, 0, 0, 0))
    sh = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(sh).rounded_rectangle((pad, pad + 10, pad + w, pad + h + 10), radius=radius + border, fill=(0, 0, 0, 120))
    sh = sh.filter(ImageFilter.GaussianBlur(16))
    img.alpha_composite(sh)
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((pad - border, pad - border, pad + w + border, pad + h + border), radius=radius + border,
                        outline=_rgba(color), width=border)
    img.save(out)
    return out, pad


def graphic_card(headline, label, style, out: Path, w=1080, h=1920, kind="full"):
    """Typographic graphic used when no matching footage exists. Clearly a graphic, never a fake screenshot."""
    pal = style["palette"]
    img = Image.new("RGBA", (w, h), _rgba(pal["primary"]))
    d = ImageDraw.Draw(img)
    # subtle grid texture
    for x in range(0, w, 60):
        d.line((x, 0, x, h), fill=_rgba(pal["cream"], 10))
    for y in range(0, h, 60):
        d.line((0, y, w, y), fill=_rgba(pal["cream"], 10))
    lab = font("Inter Medium", int(w * 0.035))
    d.text((w * 0.08, h * 0.12), (label or "").upper(), font=lab, fill=_rgba(pal["gold"]))
    words = headline.split()
    lines, cur = [], ""
    big = int(w * 0.13)
    f = font("Instrument Serif", big)
    for word in words:
        t = (cur + " " + word).strip()
        if d.textlength(t, font=f) > w * 0.84 and cur:
            lines.append(cur)
            cur = word
        else:
            cur = t
    lines.append(cur)
    y = h * 0.5 - len(lines) * big * 0.5
    for i, ln in enumerate(lines[:5]):
        ff = font("Instrument Serif Italic" if i == len(lines) - 1 and len(lines) > 1 else "Instrument Serif", big)
        d.text((w * 0.08, y), ln, font=ff, fill=_rgba(pal["gold"] if i == len(lines) - 1 and len(lines) > 1 else pal["cream"]))
        y += big * 1.0
    d.line((w * 0.08, y + 30, w * 0.4, y + 30), fill=_rgba(pal["gold"]), width=6)
    img.convert("RGB").save(out, quality=92)
    return out
