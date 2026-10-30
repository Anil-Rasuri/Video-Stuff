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
ENTRIES = (
    "none", "fade", "pop", "slide_up", "zoom", "blur_in", "slide_left", "slide_right", "drop", "flip", "wobble",
    "elastic", "bounce", "swing", "spin", "wipe_right", "curtain", "glitch",
)
EFFECTS = ("none", "pulse", "sway")  # continuous motion while the caption is on screen

# Colour effects the user can pick: per-word colour cycles, or vertical gradients.
COLOR_EFFECTS = {
    "rainbow": ("palette", ("#FF5252", "#FFB300", "#FFEB3B", "#69F0AE", "#40C4FF", "#B388FF")),
    "candy": ("palette", ("#FF80AB", "#80D8FF", "#CCFF90", "#FFE57F", "#EA80FC")),
    "sunset": ("palette", ("#FF6F00", "#FF1744", "#F50057", "#FFD740")),
    "fire": ("gradient", ("#FFF59D", "#FF9800", "#E53935")),
    "gold": ("gradient", ("#FFF9C4", "#FFC107", "#B8860B")),
    "ocean": ("gradient", ("#E0F7FA", "#26C6DA", "#1565C0")),
    "bubblegum": ("gradient", ("#FFC1E3", "#FF4DA6", "#8E24AA")),
    "mint": ("gradient", ("#F1FFE0", "#69F0AE", "#00897B")),
}
COLOR_EFFECT_LABELS = {
    "rainbow": "Rainbow words", "candy": "Candy words", "sunset": "Sunset words",
    "fire": "Gradient: fire", "gold": "Gradient: gold", "ocean": "Gradient: ocean",
    "bubblegum": "Gradient: bubblegum", "mint": "Gradient: mint",
}
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
    word_spacing: float = 1.0  # multiplier for the gap between words
    palette: tuple = ()  # colours cycled per word (rainbow look)
    gradient: tuple = ()  # 2-3 colours, top to bottom (static mode only)
    border2_color: Optional[str] = None  # second, wider outline (sticker look)
    border2: float = 0.10  # extra width of that outline, fraction of font size
    shadow_color: Optional[str] = None  # solid coloured drop shadow (3D look)
    effect: str = "none"  # see EFFECTS


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
        Preset(
            key="comic",
            label="Comic burst",
            description="Chunky comic lettering that wobbles in. Loud and fun.",
            mode="static",
            entry="wobble",
            latin_font="Bangers",
            telugu_font="Ravi Prakash",
            devanagari_font="Kalam",
            size=0.085,
            base_color="#FFEB3B",
            outline_color="#1B1B1B",
            outline=0.10,
            shadow=0.05,
            uppercase=True,
            bold=False,
        ),
        Preset(
            key="marker",
            label="Marker karaoke",
            description="Hand-drawn marker lettering; words light up orange and blur into focus.",
            mode="karaoke",
            entry="blur_in",
            latin_font="Permanent Marker",
            telugu_font="Lakki Reddy",
            devanagari_font="Kalam",
            size=0.075,
            highlight_color="#FF7A00",
            outline=0.07,
            bold=False,
        ),
        Preset(
            key="elegant",
            label="Elegant script",
            description="Graceful script text that zooms gently into place.",
            mode="static",
            entry="zoom",
            latin_font="Great Vibes",
            telugu_font="Peddana",
            devanagari_font="Sahitya",
            size=0.085,
            base_color="#FDF6E3",
            outline_color="#3B2A1A",
            outline=0.07,
            bold=False,
        ),
        Preset(
            key="impact",
            label="Impact word-pop",
            description="Heavy block letters; the spoken word flashes cyan. Cards flip in.",
            mode="word_highlight",
            entry="flip",
            latin_font="Bungee",
            telugu_font="Ramaraja",
            devanagari_font="Khand",
            size=0.075,
            highlight_color="#00E5FF",
            outline=0.09,
            shadow=0.04,
            active_scale=1.1,
            position="middle",
            bold=False,
            uppercase=True,
        ),
        Preset(
            key="dream",
            label="Dreamy reveal",
            description="Soft rounded text; words appear one by one, sliding in from the right.",
            mode="word_reveal",
            entry="slide_right",
            latin_font="Righteous",
            telugu_font="Timmana",
            devanagari_font="Palanquin",
            size=0.075,
            highlight_color="#FF4DA6",
            outline_color="#2A0F3B",
            outline=0.08,
            bold=False,
        ),
        Preset(
            key="rainbow",
            label="Rainbow words",
            description="Every word in a different bright colour, bouncy elastic entrance.",
            mode="static",
            entry="elastic",
            latin_font="Lilita One",
            telugu_font="Ramabhadra",
            devanagari_font="Modak",
            size=0.085,
            outline_color="#1A1A1A",
            outline=0.11,
            shadow=0.04,
            bold=False,
            palette=COLOR_EFFECTS["rainbow"][1],
        ),
        Preset(
            key="fire",
            label="Fire gradient 3D",
            description="Yellow-to-red gradient letters with a dark red 3D shadow.",
            mode="static",
            entry="zoom",
            latin_font="Bebas Neue",
            telugu_font="Gurajada",
            devanagari_font="Rozha One",
            size=0.095,
            outline_color="#3B0A00",
            outline=0.07,
            shadow=0.07,
            shadow_color="#7F0000",
            uppercase=True,
            bold=False,
            gradient=COLOR_EFFECTS["fire"][1],
        ),
        Preset(
            key="gold3d",
            label="Gold 3D",
            description="Shiny gold lettering with a heavy bronze shadow; swings in like a sign.",
            mode="static",
            entry="swing",
            latin_font="Rozha One",
            telugu_font="Ramaraja",
            devanagari_font="Rozha One",
            size=0.09,
            outline_color="#3B2A00",
            outline=0.05,
            shadow=0.07,
            shadow_color="#6D4C00",
            bold=False,
            gradient=COLOR_EFFECTS["gold"][1],
        ),
        Preset(
            key="ocean",
            label="Ocean gradient",
            description="Cool aqua-to-blue gradient with a white sticker border; blurs into focus.",
            mode="static",
            entry="blur_in",
            latin_font="Righteous",
            telugu_font="Timmana",
            devanagari_font="Palanquin",
            size=0.085,
            outline_color="#0B2E5C",
            outline=0.06,
            border2_color="#FFFFFF",
            border2=0.09,
            bold=False,
            gradient=COLOR_EFFECTS["ocean"][1],
        ),
        Preset(
            key="sticker",
            label="Candy sticker",
            description="Pastel candy-coloured words with a thick white sticker outline; bounces in.",
            mode="static",
            entry="bounce",
            latin_font="Lilita One",
            telugu_font="Gurajada",
            devanagari_font="Modak",
            size=0.085,
            outline_color="#4A148C",
            outline=0.07,
            border2_color="#FFFFFF",
            border2=0.12,
            shadow=0.0,
            bold=False,
            palette=COLOR_EFFECTS["candy"][1],
        ),
        Preset(
            key="cyber",
            label="Cyber glitch",
            description="Word-by-word green highlight; each line glitches in. Great for reels.",
            mode="word_highlight",
            entry="glitch",
            latin_font="Bungee",
            telugu_font="Ravi Prakash",
            devanagari_font="Khand",
            size=0.07,
            highlight_color="#39FF14",
            outline_color="#101010",
            outline=0.10,
            shadow=0.05,
            active_scale=1.12,
            uppercase=True,
            bold=False,
            position="middle",
        ),
        Preset(
            key="retro3d",
            label="Retro 3D",
            description="Yellow arcade lettering with a hot-pink block shadow; spins in.",
            mode="static",
            entry="spin",
            latin_font="Press Start 2P",
            telugu_font="Suravaram",
            devanagari_font="Tillana",
            size=0.055,
            base_color="#FFEB3B",
            outline_color="#1B1B1B",
            outline=0.09,
            shadow=0.09,
            shadow_color="#FF2E63",
            bold=False,
        ),
        Preset(
            key="karaoke_rainbow",
            label="Rainbow karaoke",
            description="Words wait in rainbow colours and turn white as they are sung; pulses to the beat.",
            mode="karaoke",
            entry="fade",
            latin_font="Lilita One",
            telugu_font="Mandali",
            devanagari_font="Kalam",
            size=0.08,
            base_color="#FFFFFF",
            highlight_color="#FFFFFF",
            outline_color="#1A1A1A",
            outline=0.10,
            shadow=0.04,
            bold=False,
            effect="pulse",
            palette=COLOR_EFFECTS["rainbow"][1],
        ),
        Preset(
            key="royal",
            label="Royal calligraphy",
            description="Elegant calligraphy with a double gold border; opens like a curtain.",
            mode="static",
            entry="curtain",
            latin_font="Great Vibes",
            telugu_font="Peddana",
            devanagari_font="Kalam",
            size=0.09,
            base_color="#FFF8E1",
            outline_color="#3E2723",
            outline=0.06,
            border2_color="#D4AF37",
            border2=0.09,
            bold=False,
            effect="sway",
        ),
        Preset(
            key="beat",
            label="Beat pulse",
            description="Big glowing text that pulses like a heartbeat. Made for music videos.",
            mode="static",
            entry="elastic",
            latin_font="Bungee",
            telugu_font="Ramabhadra",
            devanagari_font="Modak",
            size=0.08,
            outline_color="#2A0F3B",
            outline=0.08,
            glow_color="#FF2BD6",
            uppercase=True,
            bold=False,
            effect="pulse",
            position="middle",
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
    word_spacing: float = 1.0
    effect: Optional[str] = None
    color_effect: Optional[str] = None


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

    if opts.effect:
        if opts.effect not in EFFECTS:
            raise ValueError("Unknown effect %r. Choose from: %s" % (opts.effect, ", ".join(EFFECTS)))
        changes["effect"] = opts.effect
    base = PRESETS[opts.preset]
    if opts.color_effect and opts.color_effect != "none":
        if opts.color_effect not in COLOR_EFFECTS:
            raise ValueError(
                "Unknown colour effect %r. Choose from: %s" % (opts.color_effect, ", ".join(COLOR_EFFECTS))
            )
        kind, cols = COLOR_EFFECTS[opts.color_effect]
        mode = base.mode
        if kind == "gradient" and mode == "static":
            changes["gradient"], changes["palette"] = cols, ()
        else:  # gradients only work on whole lines; otherwise cycle the colours per word
            changes["palette"], changes["gradient"] = cols, ()
    scale = opts.size_scale or 1.0
    changes["size"] = base.size * max(0.3, min(3.0, float(scale)))
    changes["word_spacing"] = base.word_spacing * max(0.3, min(4.0, float(opts.word_spacing or 1.0)))
    style = dataclasses.replace(base, **changes)

    # Scale animations need a per-word layout; fall back to a fade for word modes.
    scale_based = ("pop", "zoom", "elastic", "bounce", "spin", "glitch")
    if style.mode in ("word_highlight", "word_reveal") and style.entry in scale_based:
        style = dataclasses.replace(style, entry="fade")
    # gradient bands use a clip rectangle, which the wipe animations also need
    if style.gradient and style.entry in ("wipe_right", "curtain"):
        style = dataclasses.replace(style, entry="fade")
    return style
