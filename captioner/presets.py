"""Caption style presets and user overrides.

A preset combines a *mode* (how words are revealed / highlighted), an *entry
animation*, fonts per script (Latin / Telugu / Devanagari), colours and sizes.
"""

from __future__ import annotations

import dataclasses
import re
from dataclasses import dataclass
from typing import Dict, List, Optional

MODES = ("static", "karaoke", "word_highlight", "word_reveal")
ENTRIES = ("none", "fade", "pop", "slide_up")
POSITIONS = ("bottom", "middle", "top")


@dataclass(frozen=True)
class Preset:
    key: str
    label: str
    description: str
    mode: str = "static"  # see MODES
    entry: str = "fade"  # see ENTRIES
    latin_font: str = "Poppins"
    telugu_font: str = "Mandali"
    devanagari_font: str = "Hind"
    size: float = 0.07  # font size as a fraction of min(width, height)
    base_color: str = "#FFFFFF"
    highlight_color: str = "#FFD400"
    outline_color: str = "#000000"
    back_color: str = "#000000"
    outline: float = 0.07  # outline thickness as a fraction of font size
    shadow: float = 0.03
    blur: float = 0.0
    bold: bool = True
    italic: bool = False
    uppercase: bool = False
    box: bool = False  # opaque box behind the text
    box_alpha: int = 0x60  # 0 = solid, 255 = invisible
    glow_color: Optional[str] = None
    active_scale: float = 1.0  # scale of the highlighted word (word_highlight)
    position: str = "bottom"
    margin_v: float = 0.10  # distance from top/bottom edge, fraction of min(w, h)
    spacing: float = 0.0


PRESETS: Dict[str, Preset] = {
    p.key: p
    for p in [
        Preset(
            key="classic",
            label="Classic subtitle",
            description="Clean white text with a dark outline and a soft fade.",
            mode="static",
            entry="fade",
            latin_font="Poppins",
            telugu_font="Mandali",
            devanagari_font="Hind",
            size=0.060,
            outline=0.08,
        ),
        Preset(
            key="karaoke",
            label="Karaoke lyrics (colour sweep)",
            description="The whole line is shown and each word fills with colour exactly as it is sung.",
            mode="karaoke",
            entry="fade",
            latin_font="Poppins",
            telugu_font="Ramabhadra",
            devanagari_font="Hind",
            size=0.068,
            base_color="#FFFFFF",
            highlight_color="#FFD400",
            outline=0.08,
        ),
        Preset(
            key="tiktok",
            label="Word highlight (Reels / TikTok)",
            description="Big centred text; the word being spoken pops in a bright colour.",
            mode="word_highlight",
            entry="fade",
            latin_font="Anton",
            telugu_font="Gurajada",
            devanagari_font="Mukta",
            size=0.085,
            highlight_color="#FFE600",
            outline=0.10,
            shadow=0.04,
            uppercase=True,
            active_scale=1.12,
            position="middle",
        ),
        Preset(
            key="reveal",
            label="Word-by-word reveal",
            description="Words fade and pop in one at a time as they are spoken.",
            mode="word_reveal",
            entry="fade",
            latin_font="Poppins",
            telugu_font="Suravaram",
            devanagari_font="Hind",
            size=0.075,
            highlight_color="#FF6B6B",
            outline=0.08,
        ),
        Preset(
            key="pop",
            label="Pop-in lines",
            description="Each line bounces in with a little overshoot.",
            mode="static",
            entry="pop",
            latin_font="Lobster",
            telugu_font="NTR",
            devanagari_font="Yatra One",
            size=0.082,
            base_color="#FFF3B0",
            outline_color="#5B2A00",
            outline=0.09,
            bold=False,
        ),
        Preset(
            key="slideup",
            label="Slide-up script",
            description="Elegant script font; each line glides up into place.",
            mode="static",
            entry="slide_up",
            latin_font="Pacifico",
            telugu_font="Dhurjati",
            devanagari_font="Rozha One",
            size=0.075,
            outline_color="#10223F",
            outline=0.08,
            bold=False,
        ),
        Preset(
            key="neon",
            label="Neon glow karaoke",
            description="Glowing neon colour sweep, great for music videos.",
            mode="karaoke",
            entry="fade",
            latin_font="Bebas Neue",
            telugu_font="Gurajada",
            devanagari_font="Rozha One",
            size=0.085,
            base_color="#FFFFFF",
            highlight_color="#5CF2FF",
            outline_color="#3A0B33",
            outline=0.03,
            shadow=0.0,
            blur=0.8,
            uppercase=True,
            glow_color="#FF2BD6",
            bold=False,
        ),
        Preset(
            key="boxed",
            label="Boxed caption",
            description="White text on a semi-transparent black box. Maximum readability.",
            mode="static",
            entry="fade",
            latin_font="Poppins",
            telugu_font="Mandali",
            devanagari_font="Hind",
            size=0.052,
            outline=0.28,  # box padding
            shadow=0.0,
            box=True,
            box_alpha=0x66,
            bold=False,
        ),
    ]
}

PRESET_ORDER: List[str] = list(PRESETS)


@dataclass
class StyleOptions:
    """What the user picks in the UI / CLI. ``None`` means 'use the preset's value'."""

    preset: str = "karaoke"
    animation: Optional[str] = None
    latin_font: Optional[str] = None
    telugu_font: Optional[str] = None
    devanagari_font: Optional[str] = None
    base_color: Optional[str] = None
    highlight_color: Optional[str] = None
    outline_color: Optional[str] = None
    size_scale: float = 1.0
    position: Optional[str] = None
    uppercase: Optional[bool] = None


_RGB_FUNC = re.compile(r"rgba?\(\s*([\d.]+)\s*,\s*([\d.]+)\s*,\s*([\d.]+)")


def normalize_color(value: Optional[str]) -> Optional[str]:
    """Accept '#abc', '#aabbcc' or 'rgb(r,g,b)' and return '#AABBCC' (or None)."""
    if not value:
        return None
    v = str(value).strip()
    m = _RGB_FUNC.match(v)
    if m:
        r, g, b = (max(0, min(255, int(round(float(x))))) for x in m.groups())
        return "#%02X%02X%02X" % (r, g, b)
    v = v.lstrip("#")
    if re.fullmatch(r"[0-9a-fA-F]{3}", v):
        v = "".join(ch * 2 for ch in v)
    if re.fullmatch(r"[0-9a-fA-F]{6}", v):
        return "#" + v.upper()
    raise ValueError("Invalid colour: %r (use #RRGGBB)" % value)


def resolve_style(opts: StyleOptions) -> Preset:
    """Merge a preset with the user's overrides into one concrete style."""
    if opts.preset not in PRESETS:
        raise ValueError("Unknown preset %r. Choose from: %s" % (opts.preset, ", ".join(PRESETS)))
    changes = {}
    if opts.animation:
        if opts.animation not in ENTRIES:
            raise ValueError("Unknown animation %r. Choose from: %s" % (opts.animation, ", ".join(ENTRIES)))
        changes["entry"] = opts.animation
    for field in ("latin_font", "telugu_font", "devanagari_font"):
        val = getattr(opts, field)
        if val:
            changes[field] = val
    for field in ("base_color", "highlight_color", "outline_color"):
        val = normalize_color(getattr(opts, field))
        if val:
            changes[field] = val
    if opts.position:
        if opts.position not in POSITIONS:
            raise ValueError("Unknown position %r. Choose from: %s" % (opts.position, ", ".join(POSITIONS)))
        changes["position"] = opts.position
    if opts.uppercase is not None:
        changes["uppercase"] = bool(opts.uppercase)

    base = PRESETS[opts.preset]
    scale = opts.size_scale or 1.0
    changes["size"] = base.size * max(0.3, min(3.0, float(scale)))
    style = dataclasses.replace(base, **changes)

    # Scale animations need a per-word layout; fall back to a fade for word modes.
    if style.mode in ("word_highlight", "word_reveal") and style.entry == "pop":
        style = dataclasses.replace(style, entry="fade")
    return style
