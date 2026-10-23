"""Generate animated ASS (Advanced SubStation Alpha) subtitles from timed lines.

ASS is the subtitle format that ffmpeg/libass renders with full support for
custom fonts, colours, outlines, fades, scaling, movement and karaoke timing,
which is what lets the captions stay locked to the audio.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Sequence

from .fonts import space_width_em, supports_bold
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
    dx = int(round(g.width * 0.12))
    pos = "\\pos(%d,%d)" % (g.x, g.y)
    if first:
        origin = {
            "slide_up": (g.x, g.y + g.rise),
            "drop": (g.x, g.y - 2 * g.rise),
            "slide_left": (g.x - dx, g.y),
            "slide_right": (g.x + dx, g.y),
        }.get(entry)
        if origin:
            pos = "\\move(%d,%d,%d,%d,0,%d)" % (origin[0], origin[1], g.x, g.y, d)
    parts.append(pos)
    if fade_in or fade_out:
        parts.append("\\fad(%d,%d)" % (fade_in, fade_out))

    if first:
        if entry == "pop":
            parts.append("\\fscx0\\fscy0\\t(0,150,\\fscx112\\fscy112)\\t(150,250,\\fscx100\\fscy100)")
        elif entry == "zoom":
            parts.append("\\fscx140\\fscy140\\t(0,%d,\\fscx100\\fscy100)" % (d + 100))
        elif entry == "flip":
            parts.append("\\fry90\\t(0,%d,\\fry0)" % (d + 100))
        elif entry == "wobble":
            parts.append("\\frz-8\\t(0,100,\\frz6)\\t(100,200,\\frz-3)\\t(200,300,\\frz0)")
    if first and entry == "blur_in":
        parts.append("\\blur12\\t(0,%d,\\blur%.1f)" % (d + 100, style.blur))
    elif style.blur > 0:
        parts.append("\\blur%.1f" % style.blur)
    parts.append(extra)
    return "{" + "".join(parts) + "}"


def _glow_extra(style: Preset, g: _Geo) -> str:
    return "\\1a&HFF&\\2a&HFF&\\3c%s\\bord%.1f\\blur%.1f" % (
        tag_color(style.glow_color),
        g.fs * 0.14,
        g.fs * 0.12,
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
    if style.glow_color:
        head = _head(style, True, True, dur_ms, g, extra=_glow_extra(style, g))
        events.append(_dialogue(0, ev_start, ev_end, head + body))
    head = _head(style, True, True, dur_ms, g)
    events.append(_dialogue(1, ev_start, ev_end, head + body))
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
    scale = int(round(style.active_scale * 100))

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
