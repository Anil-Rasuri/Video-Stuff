"""Optional: isolate the vocals from music with Demucs before transcribing.

Singing over loud music is the hardest case for speech recognition. Removing the
instruments first noticeably improves accuracy. This is optional and needs the
extra packages in requirements-optional.txt (PyTorch + Demucs, a large install).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def separate_vocals(audio_path, out_dir) -> Path:
    """Return the path of a vocals-only WAV. Raises RuntimeError if Demucs is unavailable."""
    audio_path, out_dir = Path(audio_path), Path(out_dir)
    try:
        import demucs  # noqa: F401
    except ImportError as exc:
        raise RuntimeError(
            "Vocal separation needs Demucs: pip install -r requirements-optional.txt"
        ) from exc

    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "demucs",
            "--two-stems=vocals",
            "-n",
            "htdemucs",
            "-o",
            str(out_dir),
            str(audio_path),
        ],
        capture_output=True,
        text=True,
    )
    vocals = out_dir / "htdemucs" / audio_path.stem / "vocals.wav"
    if proc.returncode != 0 or not vocals.exists():
        tail = "\n".join((proc.stderr or "").strip().splitlines()[-6:])
        raise RuntimeError("Demucs failed:\n" + tail)
    return vocals
