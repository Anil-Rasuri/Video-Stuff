"""High-level helpers shared by the CLI and the web app."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Callable, List, Optional, Tuple

from .models import Line, chunk_lines
from .render import check_duration, extract_audio, probe
from .transcribe import transcribe_audio


def transcribe_video(
    video,
    language: Optional[str] = None,
    model_size: str = "small",
    *,
    song: bool = False,
    max_words: int = 5,
    hint: Optional[str] = None,
    separate_vocals: bool = False,
    progress: Optional[Callable[[float, str], None]] = None,
) -> Tuple[List[Line], List[str]]:
    """Video file -> caption lines with word timing. Returns (lines, warnings)."""
    warnings: List[str] = []
    say = progress or (lambda frac, msg: None)

    info = probe(video)
    check_duration(info)

    work = Path(tempfile.mkdtemp(prefix="captioner_audio_"))
    say(0.02, "Extracting audio")
    audio = extract_audio(video, work / "audio.wav")

    if separate_vocals:
        say(0.05, "Separating vocals (this can take a minute)")
        try:
            from .vocals import separate_vocals as _separate

            audio = _separate(audio, work / "stems")
        except Exception as exc:  # fall back to the original audio
            warnings.append("Vocal separation skipped: %s" % exc)

    say(0.15, "Loading speech model (first run downloads it)")
    lines = transcribe_audio(
        audio,
        language=language,
        model_size=model_size,
        song=song,
        initial_prompt=hint,
        duration=info.duration,
        progress=lambda f: say(0.2 + 0.78 * f, "Transcribing"),
    )
    if not lines:
        warnings.append("No speech was detected. Try 'Song' mode, a larger model, or a different language.")
    return chunk_lines(lines, max_words=max_words), warnings
