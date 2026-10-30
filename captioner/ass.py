"""Generate animated ASS (Advanced SubStation Alpha) subtitles from timed lines.

ASS is the subtitle format that ffmpeg/libass renders with full support for
custom fonts, colours, outlines, fades, scaling, movement and karaoke timing,
which is what lets the captions stay locked to the audio.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Sequence

from .fonts import line_height_em, space_width_em, supports_bold
from .models import Line
from .presets import Preset
from .scripts import script_of

# --------------------------------------------------------------------------
# small helpers
# --------------------------------------------------------------------------


def _rgb(hex_color: str):
    c = hex_color.lstrip("#")
    return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)


def style_color(hex_color: str, alpha: int = 0) -> str:
    """Colour for a [V4+ Styles] line: &HAABBGGRR."""
    r, g, b = _rgb(hex_color)
    return "&H%02X%02X%02X%02X" % (alpha, b, g, r)


def tag_color(hex_color: str) -> str:
    """Colour for an inline override tag: &HBBGGRR&."""
    r, g, b = _rgb(hex_color)
    return "&H%02X%02X%02X&" % (b, g, r)


def ass_time(t: float) -> str:
    cs = max(0, int(round(t * 100)))
    h, rem = divmod(cs, 360000)
    m, rem = divmod(rem, 6000)
    s, c = divmod(rem, 100)
    return "%d:%02d:%02d.%02d" % (h, m, s, c)


def _esc(text: str) -> str:
    """Make a word safe to place inside an ASS dialogue line."""
    return (
        text.replace("\\", "")
        .replace("{", "(")
        .replace("}", ")")
        .replace("\r", " ")
        .replace("\n", " ")
    )


@dataclass
class _Geo:
    width: int
    height: int
    fs: int
    align: int
    x: int
    y: int
    rise: int  # slide-up travel distance in px


_DEFAULT_LINE_EM = {"latin": 1.3, "telugu": 1.6, "devanagari": 1.7}


def _band_limits(style: Preset, texts, fams, g: "_Geo"):
    """(top, bottom) pixel rows where the glyphs of a caption line sit, for gradient bands."""
    scripts = {script_of(t) for t in texts} or {"latin"}
    h_em = max((line_height_em(fams[sc]) or _DEFAULT_LINE_EM[sc]) for sc in scripts)
    h = h_em * g.fs
    if g.align == 2:  # bottom-anchored
        bottom, top = g.y, g.y - h
    elif g.align == 8:  # top-anchored
        top, bottom = g.y, g.y + h
    else:  # middle
        top, bottom = g.y - h / 2.0, g.y + h / 2.0
    # glyph ink sits a little inside the line box
    return top + 0.16 * h, bottom - 0.14 * h


def _fams(style: Preset):
    return {
        "latin": style.latin_font,
        "telugu": style.telugu_font,
        "devanagari": style.devanagari_font,
    }


def _font_tag(word: str, style: Preset, fams) -> tuple:
    """Return (key, tag) selecting the right font + weight for this word's script."""
    fam = fams[script_of(word)]
    bold = 1 if (style.bold and supports_bold(fam)) else 0
    return (fam, bold), "\\fn%s\\b%d" % (fam, bold)


# --------------------------------------------------------------------------
# per-event header: position, entry animation, fades
# --------------------------------------------------------------------------


# Entry animations that also fade in.
FADE_IN_ENTRIES = (
    "fade", "slide_up", "zoom", "blur_in", "slide_left", "slide_right", "drop", "flip", "wobble",
    "bounce", "swing", "spin", "glitch",
)

# Wanted width of the gap between words (em). Narrow-spaced fonts are widened to this.
SPACE_TARGET_EM = 0.30
_DEFAULT_SPACE_EM = {"latin": 0.27, "telugu": 0.12, "devanagari": 0.18}


def _gap(word: str, style: Preset, fams, g: "_Geo") -> str:
    """Separator placed after ``word``: a normal space, widened if the font's space is too narrow."""
    script = script_of(word)
    width = space_width_em(fams[script])
    if width is None:
        width = _DEFAULT_SPACE_EM[script]
    extra_em = SPACE_TARGET_EM * style.word_spacing - width
    if extra_em < 0.04:
        return " "
    return "{\\fsp%.1f} {\\fsp%.1f}" % (extra_em * g.fs, style.spacing * g.fs)


def _entry(entry: str, style: Preset, g: "_Geo", d: int):
    """(position tag, extra transform tags) for the entry animation ``entry``.

    ``d`` is how long (ms) the movement may take.
    """
    dx = int(round(g.width * 0.12))
    pos = "\\pos(%d,%d)" % (g.x, g.y)
    tags = ""
    moves = {
        "slide_up": (g.x, g.y + g.rise),
        "drop": (g.x, g.y - 2 * g.rise),
        "slide_left": (g.x - dx, g.y),
        "slide_right": (g.x + dx, g.y),
        "bounce": (g.x, g.y - 4 * g.rise),
    }
    if entry in moves:
        o = moves[entry]
        dd = d if entry != "bounce" else max(120, min(220, d))
        pos = "\\move(%d,%d,%d,%d,0,%d)" % (o[0], o[1], g.x, g.y, dd)
    if entry == "pop":
        tags = "\\fscx0\\fscy0\\t(0,150,\\fscx112\\fscy112)\\t(150,250,\\fscx100\\fscy100)"
    elif entry == "zoom":
        tags = "\\fscx140\\fscy140\\t(0,%d,\\fscx100\\fscy100)" % (d + 100)
    elif entry == "elastic":
        tags = (
            "\\fscx0\\fscy0\\t(0,120,\\fscx126\\fscy126)\\t(120,200,\\fscx90\\fscy90)"
            "\\t(200,270,\\fscx106\\fscy106)\\t(270,330,\\fscx100\\fscy100)"
        )
    elif entry == "bounce":
        dd = max(120, min(220, d))
        tags = "\\t(%d,%d,\\fscx118\\fscy82)\\t(%d,%d,\\fscx100\\fscy100)" % (dd, dd + 70, dd + 70, dd + 190)
    elif entry == "flip":
        tags = "\\fry90\\t(0,%d,\\fry0)" % (d + 100)
    elif entry == "wobble":
        tags = "\\frz-8\\t(0,100,\\frz6)\\t(100,200,\\frz-3)\\t(200,300,\\frz0)"
    elif entry == "swing":  # pendulum: rotate about a point above the text
        tags = "\\org(%d,%d)\\frz-24\\t(0,%d,\\frz5)\\t(%d,%d,\\frz0)" % (
            g.x, g.y - 4 * g.fs, d + 120, d + 120, d + 300)
    elif entry == "spin":
        cy = {2: g.y - int(0.6 * g.fs), 8: g.y + int(0.6 * g.fs)}.get(g.align, g.y)
        tags = "\\org(%d,%d)\\frz-300\\fscx20\\fscy20\\t(0,%d,\\frz0\\fscx100\\fscy100)" % (g.x, cy, d + 200)
    elif entry == "glitch":
        tags = (
            "\\frz-4\\fscx112\\t(0,70,\\frz4\\fscx92)\\t(70,140,\\frz-2\\fscx106)"
            "\\t(140,210,\\frz1\\fscx98)\\t(210,260,\\frz0\\fscx100)"
        )
    elif entry == "wipe_right":
        x0, x1 = int(g.width * 0.04), int(g.width * 0.96)
        tags = "\\clip(%d,0,%d,%d)\\t(0,%d,\\clip(%d,0,%d,%d))" % (x0, x0, g.height, d + 250, x0, x1, g.height)
    elif entry == "curtain":
        x0, x1, mid = int(g.width * 0.04), int(g.width * 0.96), g.width // 2
        tags = "\\clip(%d,0,%d,%d)\\t(0,%d,\\clip(%d,0,%d,%d))" % (mid, mid, g.height, d + 250, x0, x1, g.height)
    return pos, tags


def _effect(style: Preset, dur_ms: int) -> str:
    """Continuous effect (pulse / sway) as \\t keyframes after the entry has finished."""
    if style.effect == "none" or style.mode not in ("static", "karaoke"):
        return ""
    out = []
    if style.effect == "pulse":  # heartbeat-like scale beat
        t = 350
        while t + 300 < dur_ms and len(out) < 60:
            out.append("\\t(%d,%d,\\fscx107\\fscy107)\\t(%d,%d,\\fscx100\\fscy100)" % (t, t + 110, t + 110, t + 300))
            t += 500
    elif style.effect == "sway":  # gentle rocking
        t, sign = 350, 1
        while t + 600 < dur_ms and len(out) < 60:
            out.append("\\t(%d,%d,\\frz%d)" % (t, t + 600, 2 * sign))
            t += 600
            sign = -sign
    return "".join(out)


def _head(style: Preset, first: bool, last: bool, dur_ms: int, g: _Geo, entry=None, extra="") -> str:
    entry = style.entry if entry is None else entry
    parts = ["\\an%d" % g.align]
    fade_in = fade_out = 0
    if entry != "none":
        if first and entry in FADE_IN_ENTRIES:
            fade_in = 150
        if last:
            fade_out = 120
    total = fade_in + fade_out
    cap = int(dur_ms * 0.8)
    if total > cap and total > 0:
        k = cap / float(total)
        fade_in, fade_out = int(fade_in * k), int(fade_out * k)

    d = max(60, min(260, int(dur_ms)))  # how long the entry movement takes (ms)
    pos, tags = _entry(entry, style, g, d) if first else ("\\pos(%d,%d)" % (g.x, g.y), "")
    parts.append(pos)
    if fade_in or fade_out:
        parts.append("\\fad(%d,%d)" % (fade_in, fade_out))
    parts.append(tags)
    if first and entry == "blur_in":
        parts.append("\\blur12\\t(0,%d,\\blur%.1f)" % (d + 100, style.blur))
    elif style.blur > 0:
        parts.append("\\blur%.1f" % style.blur)
    if first:
        parts.append(_effect(style, dur_ms))
    parts.append(extra)
    return "{" + "".join(parts) + "}"


def _glow_extra(style: Preset, g: _Geo) -> str:
    return "\\1a&HFF&\\2a&HFF&\\3c%s\\bord%.1f\\blur%.1f" % (
        tag_color(style.glow_color),
        g.fs * 0.14,
        g.fs * 0.12,
    )


def _border2_extra(style: Preset, g: _Geo) -> str:
    """Second, wider coloured outline drawn underneath the normal one."""
    return "\\1a&HFF&\\2a&HFF&\\3c%s\\bord%.1f\\shad0" % (
        tag_color(style.border2_color),
        g.fs * (style.outline + style.border2),
    )


def _dialogue(layer: int, start: float, end: float, text: str) -> str:
    return "Dialogue: %d,%s,%s,Cap,,0,0,0,,%s" % (layer, ass_time(start), ass_time(end), text)


# --------------------------------------------------------------------------
# modes
# --------------------------------------------------------------------------


def _inline_text(texts: Sequence[str], style: Preset, fams, base_key, g, karaoke_cs=None, lead_cs=0) -> str:
    """Whole line as inline text, switching font per script; optional \\kf timing."""
    out: List[str] = []
    cur = base_key
    if karaoke_cs is not None and lead_cs > 0:
        out.append("{\\k%d}" % lead_cs)
    for i, word in enumerate(texts):
        key, ftag = _font_tag(word, style, fams)
        tags = ""
        if karaoke_cs is not None:
            tags += "\\kf%d" % karaoke_cs[i]
        if style.palette:  # colourful words: unsung colour in karaoke, fill colour otherwise
            tags += ("\\2c%s" if karaoke_cs is not None else "\\1c%s") % tag_color(style.palette[i % len(style.palette)])
        if key != cur:
            tags += ftag
            cur = key
        if tags:
            out.append("{" + tags + "}")
        out.append(word + (_gap(word, style, fams, g) if i < len(texts) - 1 else ""))
    return "".join(out)


def _static_or_karaoke(line, texts, ev_start, ev_end, style, g, fams, base_key) -> List[str]:
    dur_ms = int((ev_end - ev_start) * 1000)
    karaoke = style.mode == "karaoke"
    cs = None
    lead_cs = 0
    if karaoke:
        bounds = [int(round((w.start - ev_start) * 100)) for w in line.words]
        bounds = [max(0, b) for b in bounds]
        for i in range(1, len(bounds)):  # keep monotonic
            bounds[i] = max(bounds[i], bounds[i - 1])
        end_b = max(bounds[-1], int(round((line.end - ev_start) * 100)))
        lead_cs = bounds[0]
        cs = [(bounds[i + 1] if i + 1 < len(bounds) else end_b) - bounds[i] for i in range(len(bounds))]
    body = _inline_text(texts, style, fams, base_key, g, cs, lead_cs)

    events = []
    grad = style.gradient if (style.mode == "static" and len(style.gradient) >= 2) else ()
    if style.glow_color:
        head = _head(style, True, True, dur_ms, g, extra=_glow_extra(style, g))
        events.append(_dialogue(0, ev_start, ev_end, head + body))
    if style.border2_color:
        head = _head(style, True, True, dur_ms, g, extra=_border2_extra(style, g))
        events.append(_dialogue(0, ev_start, ev_end, head + body))
    head = _head(style, True, True, dur_ms, g, extra=("\\1c%s" % tag_color(grad[0])) if grad else "")
    events.append(_dialogue(1, ev_start, ev_end, head + body))
    if grad:  # vertical colour bands: overlay clipped copies of the text
        top, bottom = _band_limits(style, texts, fams, g)
        n = len(grad)
        cuts = [top + (bottom - top) * k / float(n) for k in range(1, n)] + [g.height]
        for k in range(1, n):
            y0, y1 = int(round(cuts[k - 1])) - 1, int(round(cuts[k]))
            extra = "\\1c%s\\bord0\\shad0\\clip(0,%d,%d,%d)" % (tag_color(grad[k]), y0, g.width, y1)
            head = _head(style, True, True, dur_ms, g, extra=extra)
            events.append(_dialogue(1 + k, ev_start, ev_end, head + body))
    return events


def _word_events(line, texts, ev_start, ev_end, style, g, fams) -> List[str]:
    n = len(texts)
    reveal = style.mode == "word_reveal"
    starts = [w.start for w in line.words]

    spans = []  # (start, end, active_index)
    if not reveal and starts[0] - ev_start > 0.04:
        spans.append((ev_start, starts[0], -1))
    for i in range(n):
        s = max(starts[i], ev_start)
        e = min(starts[i + 1] if i + 1 < n else ev_end, ev_end)
        if e - s >= 0.03:
            spans.append((s, e, i))
    if not spans:
        spans = [(ev_start, ev_end, -1)]

    base = tag_color(style.base_color)
    hl = tag_color(style.highlight_color)
    pal = [tag_color(c) for c in style.palette]
    scale = int(round(style.active_scale * 100))

    base_default = base
    events = []
    for k, (s, e, active) in enumerate(spans):
        first, last = k == 0, k == len(spans) - 1
        dur_ms = int((e - s) * 1000)
        # Reveal mode has its own per-word animation; only keep the exit fade.
        entry = "none" if (reveal and first and not last) else style.entry
        if reveal and first and last:
            entry = style.entry
        head = _head(style, first, last, dur_ms, g, entry=entry)
        pieces = []
        for i, word in enumerate(texts):
            _, ftag = _font_tag(word, style, fams)
            base = pal[i % len(pal)] if pal else base_default
            if reveal:
                if i > active:
                    tags = ftag + "\\alpha&HFF&"
                elif i == active:
                    tags = (
                        ftag
                        + "\\alpha&HFF&\\c%s\\fscx80\\fscy80\\t(0,160,\\alpha&H00&\\fscx100\\fscy100)" % hl
                    )
                else:
                    tags = ftag + "\\alpha&H00&\\c%s\\fscx100\\fscy100" % base
            else:
                if i == active:
                    tags = ftag + "\\c%s\\fscx%d\\fscy%d" % (hl, scale, scale)
                else:
                    tags = ftag + "\\c%s\\fscx100\\fscy100" % base
            pieces.append("{" + tags + "}" + word + (_gap(word, style, fams, g) if i < n - 1 else ""))
        events.append(_dialogue(0, s, e, head + "".join(pieces)))
    return events


# --------------------------------------------------------------------------
# public entry point
# --------------------------------------------------------------------------


def build_ass(
    lines: Sequence[Line],
    width: int,
    height: int,
    style: Preset,
    *,
    hold: float = 0.25,
    lead: float = 0.15,
) -> str:
    """Return the full text of an .ass file for the given lines and style."""
    lines = sorted((l for l in lines if l.words), key=lambda l: l.start)
    unit = min(width, height)
    fs = max(12, int(round(style.size * unit)))
    mlr = int(round(width * 0.06))
    mv = int(round(unit * style.margin_v))
    align = {"bottom": 2, "middle": 5, "top": 8}[style.position]
    x = int(round(width / 2))
    y = {"bottom": height - mv, "middle": int(round(height / 2)), "top": mv}[style.position]
    g = _Geo(width, height, fs, align, x, y, rise=int(round(unit * 0.05)))

    fams = _fams(style)
    base_bold = -1 if (style.bold and supports_bold(style.latin_font)) else 0
    base_key = (style.latin_font, 1 if base_bold else 0)

    karaoke = style.mode == "karaoke"
    primary = style_color(style.highlight_color if karaoke else style.base_color)
    secondary = style_color(style.base_color if karaoke else style.highlight_color)
    if style.box:
        border_style, outline_w, shadow_w = 3, fs * style.outline, 0.0
        outline_c = style_color(style.outline_color, style.box_alpha)
        back_c = style_color(style.back_color, 0xFF)
    else:
        border_style, outline_w, shadow_w = 1, fs * style.outline, fs * style.shadow
        outline_c = style_color(style.outline_color)
        back_c = style_color(style.back_color, 0x60)
        if style.shadow_color:  # solid coloured drop shadow (3D look)
            back_c = style_color(style.shadow_color, 0)

    header = [
        "[Script Info]",
        "; Generated by video-captioner",
        "ScriptType: v4.00+",
        "PlayResX: %d" % width,
        "PlayResY: %d" % height,
        "WrapStyle: 0",
        "ScaledBorderAndShadow: yes",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
        "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, "
        "Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        "Style: Cap,%s,%d,%s,%s,%s,%s,%d,%d,0,0,100,100,%.1f,0,%d,%.1f,%.1f,%d,%d,%d,%d,1"
        % (
            style.latin_font,
            fs,
            primary,
            secondary,
            outline_c,
            back_c,
            base_bold,
            -1 if style.italic else 0,
            style.spacing * fs,
            border_style,
            outline_w,
            shadow_w,
            align,
            mlr,
            mlr,
            mv,
        ),
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]

    events: List[str] = []
    prev_end = 0.0
    for idx, line in enumerate(lines):
        nxt = lines[idx + 1].start if idx + 1 < len(lines) else None
        ev_start = max(prev_end, line.start - lead)
        ev_end = line.end + hold
        if nxt is not None:
            ev_end = min(ev_end, max(nxt, line.end))
        ev_end = max(ev_end, ev_start + 0.1)
        prev_end = ev_end

        texts = [_esc(w.text.upper() if style.uppercase else w.text) for w in line.words]
        if style.mode in ("static", "karaoke"):
            events.extend(_static_or_karaoke(line, texts, ev_start, ev_end, style, g, fams, base_key))
        else:
            events.extend(_word_events(line, texts, ev_start, ev_end, style, g, fams))

    return "\n".join(header + events) + "\n"
