"""Sample images of fonts and style presets, rendered with the same engine as the final video.

The app shows these in galleries so you can *see* a font or style before choosing it.
Images are cached in ``fonts/.previews`` and only re-rendered when something changes.
"""

from __future__ import annotations

import dataclasses
import hashlib
import shutil
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import List, Optional, Tuple

from . import fonts as fontlib
from .ass import build_ass
from .models import Line
from .presets import PRESET_ORDER, PRESETS, StyleOptions, resolve_style

CACHE_DIR = fontlib.FONT_DIR / ".previews"
VERSION = "v4"

SAMPLES = {
    "latin": "Hello Stylish World",
    "telugu": "నమస్కారం తెలుగు అక్షరాలు",
    "devanagari": "नमस्ते सहेली हिन्दी",
}
PRESET_SAMPLE = "Hello నమస్కారం नमस्ते"


def _frame(ass_text: str, families, w: int, h: int, t: float, out: Path, bg: str) -> bool:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return False
    work = Path(tempfile.mkdtemp(prefix="captioner_prev_"))
    try:
        fontlib.stage_fonts(families, work / "fonts")
        (work / "c.ass").write_text(ass_text, encoding="utf-8")
        (work / "fonts").mkdir(exist_ok=True)
        cmd = [
            ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
            "-f", "lavfi", "-i", "color=c=%s:s=%dx%d:d=%.1f:r=10" % (bg, w, h, t + 0.5),
            "-vf", "ass=c.ass:fontsdir=fonts", "-ss", "%.2f" % t, "-frames:v", "1", str(out),
        ]
        out.parent.mkdir(parents=True, exist_ok=True)
        return subprocess.run(cmd, cwd=str(work), capture_output=True).returncode == 0 and out.exists()
    finally:
        shutil.rmtree(work, ignore_errors=True)


def _key(*parts) -> str:
    return hashlib.sha1("|".join(str(p) for p in (VERSION,) + parts).encode("utf-8")).hexdigest()[:12]


def _font_stamp(family: str) -> str:
    spec = fontlib.FONTS.get(family)
    files = fontlib._local_files(spec) if spec else []
    return ",".join("%s:%d" % (f.name, f.stat().st_size) for f in files) or "system"


def font_preview(family: str, script: str) -> Optional[Path]:
    """PNG showing ``family`` rendering a sample of ``script``; cached."""
    out = CACHE_DIR / ("font_%s_%s.png" % (_key(family, script, _font_stamp(family)), script))
    if out.exists():
        return out
    base = dataclasses.replace(
        PRESETS["classic"],
        entry="none",
        size=0.36,
        outline=0.05,
        shadow=0.02,
        position="middle",
        bold=False,
        latin_font=family if script == "latin" else PRESETS["classic"].latin_font,
        telugu_font=family if script == "telugu" else PRESETS["classic"].telugu_font,
        devanagari_font=family if script == "devanagari" else PRESETS["classic"].devanagari_font,
    )
    line = Line.from_text(SAMPLES[script], 0.0, 2.0)
    ass = build_ass([line], 640, 120, base, hold=1.0, lead=0.0)
    ok = _frame(ass, [family], 640, 120, 1.0, out, "0x1b2238")
    return out if ok else None


def font_gallery(script: str, workers: int = 4) -> List[Tuple[str, str]]:
    """[(image path, family)] for every installed font that is offered for ``script``."""
    families = [f for f in fontlib.fonts_for(script) if fontlib.font_available(f)]
    with ThreadPoolExecutor(max_workers=workers) as pool:
        paths = list(pool.map(lambda fam: font_preview(fam, script), families))
    return [(str(p), fam) for p, fam in zip(paths, families) if p]


def preset_preview(key: str) -> Optional[Path]:
    style, _ = fontlib.resolve_style_fonts(resolve_style(StyleOptions(preset=key)))
    stamp = ",".join(_font_stamp(f) for f in (style.latin_font, style.telugu_font, style.devanagari_font))
    out = CACHE_DIR / ("preset_%s_%s.png" % (key, _key(repr(style), stamp)))
    if out.exists():
        return out
    line = Line.from_text(PRESET_SAMPLE, 1.0, 3.0)
    # bigger than in a real video so the style is easy to judge in a small thumbnail
    big = dataclasses.replace(style, position="middle", size=min(0.30, style.size * 2.4))
    ass = build_ass([line], 640, 220, big)
    ok = _frame(ass, [style.latin_font, style.telugu_font, style.devanagari_font], 640, 220, 2.3, out, "0x232a40")
    return out if ok else None


def preset_gallery(workers: int = 4) -> List[Tuple[str, str, str]]:
    """[(image path, label, key)] for every preset."""
    with ThreadPoolExecutor(max_workers=workers) as pool:
        paths = list(pool.map(preset_preview, PRESET_ORDER))
    return [(str(p), PRESETS[k].label, k) for p, k in zip(paths, PRESET_ORDER) if p]
