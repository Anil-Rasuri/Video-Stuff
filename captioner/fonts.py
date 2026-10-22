"""Font registry: free Google Fonts for Telugu, Hindi (Devanagari) and English.

Fonts are downloaded into ``./fonts`` (or ``$CAPTIONER_FONT_DIR``) the first time
they are needed:  ``python -m captioner fonts``.  You can also drop any ``.ttf``
files into that folder yourself. All listed fonts are licensed under the SIL
Open Font License.
"""

from __future__ import annotations

import functools
import os
import shutil
import subprocess
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
FONT_DIR = Path(os.environ.get("CAPTIONER_FONT_DIR", str(ROOT / "fonts")))

# Tried in order; the second is a CDN mirror of the same repository.
BASE_URLS = (
    "https://raw.githubusercontent.com/google/fonts/main/",
    "https://cdn.jsdelivr.net/gh/google/fonts@main/",
)


@dataclass(frozen=True)
class FontSpec:
    family: str  # exact family name inside the font file (used in ASS \fn)
    repo_dir: str  # folder inside github.com/google/fonts
    files: Tuple[str, ...]
    scripts: Tuple[str, ...]
    has_bold: bool = False  # ships a real Bold face


def _spec(family, repo_dir, files, scripts, has_bold=False) -> FontSpec:
    return FontSpec(family, repo_dir, tuple(files), tuple(scripts), has_bold)


_SPECS: List[FontSpec] = [
    # --- Telugu ---------------------------------------------------------
    _spec("Mandali", "ofl/mandali", ["Mandali-Regular.ttf"], ["telugu"]),
    _spec("Ramabhadra", "ofl/ramabhadra", ["Ramabhadra-Regular.ttf"], ["telugu"]),
    _spec("Gurajada", "ofl/gurajada", ["Gurajada-Regular.ttf"], ["telugu"]),
    _spec("Suravaram", "ofl/suravaram", ["Suravaram-Regular.ttf"], ["telugu"]),
    _spec("NTR", "ofl/ntr", ["NTR-Regular.ttf"], ["telugu"]),
    _spec("Dhurjati", "ofl/dhurjati", ["Dhurjati-Regular.ttf"], ["telugu"]),
    # --- Latin + Devanagari -----------------------------------------------
    _spec("Poppins", "ofl/poppins", ["Poppins-Regular.ttf", "Poppins-Bold.ttf"], ["latin", "devanagari"], True),
    _spec("Hind", "ofl/hind", ["Hind-Regular.ttf", "Hind-Bold.ttf"], ["devanagari", "latin"], True),
    _spec("Mukta", "ofl/mukta", ["Mukta-Regular.ttf", "Mukta-Bold.ttf"], ["devanagari", "latin"], True),
    _spec("Yatra One", "ofl/yatraone", ["YatraOne-Regular.ttf"], ["devanagari", "latin"]),
    _spec("Rozha One", "ofl/rozhaone", ["RozhaOne-Regular.ttf"], ["devanagari", "latin"]),
    # --- Latin only -------------------------------------------------------
    _spec("Anton", "ofl/anton", ["Anton-Regular.ttf"], ["latin"]),
    _spec("Bebas Neue", "ofl/bebasneue", ["BebasNeue-Regular.ttf"], ["latin"]),
    _spec("Lobster", "ofl/lobster", ["Lobster-Regular.ttf"], ["latin"]),
    _spec("Pacifico", "ofl/pacifico", ["Pacifico-Regular.ttf"], ["latin"]),
]

FONTS: Dict[str, FontSpec] = {s.family: s for s in _SPECS}


def fonts_for(script: str) -> List[str]:
    """Family names that cover a script ('latin', 'telugu', 'devanagari')."""
    return [s.family for s in _SPECS if script in s.scripts]


def supports_bold(family: str) -> bool:
    """True if bold may be requested for this family without faking it."""
    spec = FONTS.get(family)
    return True if spec is None else spec.has_bold


# --------------------------------------------------------------------------
# Availability
# --------------------------------------------------------------------------


def _local_files(spec: FontSpec) -> List[Path]:
    return [FONT_DIR / f for f in spec.files if (FONT_DIR / f).is_file()]


@functools.lru_cache(maxsize=None)
def _system_has(family: str) -> bool:
    exe = shutil.which("fc-match")
    if not exe:
        return False
    try:
        out = subprocess.run(
            [exe, "-f", "%{family}", family], capture_output=True, text=True, timeout=10
        ).stdout
    except Exception:
        return False
    names = [n.strip().lower() for n in out.replace("\n", ",").split(",")]
    return family.lower() in names


def font_available(family: str) -> bool:
    spec = FONTS.get(family)
    if spec is not None and _local_files(spec):
        return True
    return _system_has(family)


def resolve_style_fonts(style):
    """Swap in an installed font where the preset's font is missing.

    Returns ``(style, warnings)``. Never raises: if nothing suitable is
    installed the original family is kept and libass falls back to whatever
    the system offers.
    """
    import dataclasses

    changes: Dict[str, str] = {}
    warnings: List[str] = []
    for script, attr in (
        ("latin", "latin_font"),
        ("telugu", "telugu_font"),
        ("devanagari", "devanagari_font"),
    ):
        wanted = getattr(style, attr)
        if font_available(wanted):
            continue
        alt = next((f for f in fonts_for(script) if f != wanted and font_available(f)), None)
        if alt:
            changes[attr] = alt
            warnings.append("Font '%s' is not installed; using '%s' for %s text." % (wanted, alt, script))
        else:
            warnings.append(
                "No %s font installed ('%s' missing). Run `python -m captioner fonts` "
                "or copy .ttf files into %s." % (script, wanted, FONT_DIR)
            )
    return (dataclasses.replace(style, **changes) if changes else style), warnings


def stage_fonts(families: Iterable[str], dest: Path) -> List[Path]:
    """Copy the font files for ``families`` into ``dest`` (for ffmpeg's fontsdir)."""
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    copied: List[Path] = []
    for fam in dict.fromkeys(families):
        spec = FONTS.get(fam)
        if not spec:
            continue
        for src in _local_files(spec):
            target = dest / src.name
            if not target.exists():
                shutil.copy2(src, target)
            copied.append(target)
    return copied


# --------------------------------------------------------------------------
# Download
# --------------------------------------------------------------------------

_MAGIC = (b"\x00\x01\x00\x00", b"OTTO", b"true", b"ttcf")


def _fetch(url: str, timeout: float = 30.0) -> Optional[bytes]:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "video-captioner"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read()
    except Exception:
        return None


def download_fonts(
    families: Optional[Iterable[str]] = None,
    force: bool = False,
    log: Callable[[str], None] = print,
    timeout: float = 30.0,
) -> Dict[str, bool]:
    """Download fonts from the Google Fonts repository. Returns {family: ok}."""
    FONT_DIR.mkdir(parents=True, exist_ok=True)
    result: Dict[str, bool] = {}
    for fam in list(families) if families is not None else list(FONTS):
        spec = FONTS[fam]
        ok = True
        for fname in spec.files:
            dest = FONT_DIR / fname
            if dest.exists() and not force:
                continue
            data = None
            for base in BASE_URLS:
                data = _fetch(base + spec.repo_dir + "/" + fname, timeout)
                if data and data[:4] in _MAGIC:
                    break
                data = None
            if data:
                tmp = dest.with_name(dest.name + ".part")
                tmp.write_bytes(data)
                tmp.replace(dest)
                log("downloaded %s" % fname)
            else:
                ok = False
                log("could not download %s (put the .ttf into %s manually)" % (fname, FONT_DIR))
        result[fam] = ok
    return result


def download_missing(log: Callable[[str], None] = print, timeout: float = 15.0) -> Dict[str, bool]:
    """Download only the families that have no local file yet."""
    missing = [f for f, s in FONTS.items() if not _local_files(s)]
    return download_fonts(missing, log=log, timeout=timeout) if missing else {}
