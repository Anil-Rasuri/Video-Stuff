"""Speech / lyrics to timed words with faster-whisper (free, runs locally)."""

from __future__ import annotations

import functools
from typing import Callable, List, Optional

from .models import Line, Word, _spread, normalize_lines

LANGUAGES = {
    "te": "Telugu",
    "hi": "Hindi",
    "en": "English",
}

# 'turbo' models are much faster; 'medium' / 'large-v3' are the most accurate
# for Telugu. 'small' is the best size/speed trade-off on a CPU.
MODEL_SIZES = ["tiny", "base", "small", "medium", "large-v3-turbo", "large-v3"]


def _pick_device():
    try:
        import ctranslate2

        if ctranslate2.get_cuda_device_count() > 0:
            return "cuda", "float16"
    except Exception:
        pass
    return "cpu", "int8"


@functools.lru_cache(maxsize=2)
def _load_model(size: str):
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:  # pragma: no cover - depends on the environment
        raise RuntimeError(
            "faster-whisper is not installed. Run:  pip install -r requirements.txt"
        ) from exc
    device, compute_type = _pick_device()
    return WhisperModel(size, device=device, compute_type=compute_type)


def transcribe_audio(
    audio_path,
    language: Optional[str] = None,
    model_size: str = "small",
    *,
    song: bool = False,
    initial_prompt: Optional[str] = None,
    duration: Optional[float] = None,
    progress: Optional[Callable[[float], None]] = None,
) -> List[Line]:
    """Return one ``Line`` per Whisper segment, each with word-level timestamps.

    ``language`` is 'te', 'hi', 'en' or None to auto-detect. For songs the
    speech/voice-activity filter is switched off because it tends to cut out
    singing.
    """
    model = _load_model(model_size)
    segments, _info = model.transcribe(
        str(audio_path),
        language=language,
        task="transcribe",
        word_timestamps=True,
        vad_filter=not song,
        beam_size=5,
        condition_on_previous_text=False,
        initial_prompt=initial_prompt or None,
    )

    lines: List[Line] = []
    for seg in segments:
        words = [
            Word(w.word.strip(), float(w.start), float(w.end))
            for w in (seg.words or [])
            if w.word and w.word.strip()
        ]
        if not words:
            texts = (seg.text or "").split()
            if not texts:
                continue
            words = _spread(texts, float(seg.start), float(seg.end))
        lines.append(Line(words))
        if progress and duration:
            progress(min(1.0, float(seg.end) / duration))
    if progress:
        progress(1.0)
    return normalize_lines(lines)
