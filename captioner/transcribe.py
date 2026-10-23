"""Speech / lyrics to timed words with faster-whisper (free, runs locally)."""

from __future__ import annotations

import functools
import os
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

# Set to True after the GPU failed once (missing/incompatible CUDA libraries),
# so every later run goes straight to the CPU.
_gpu_failed = False


def _pick_device():
    """('cuda', 'float16') when a working-looking GPU exists, else ('cpu', 'int8').

    ``CAPTIONER_DEVICE=cpu`` (or ``cuda``) overrides the automatic choice.
    """
    pref = os.environ.get("CAPTIONER_DEVICE", "auto").strip().lower()
    if pref == "cpu" or _gpu_failed:
        return "cpu", "int8"
    if pref == "cuda":
        return "cuda", "float16"
    try:
        import ctranslate2

        if ctranslate2.get_cuda_device_count() > 0:
            return "cuda", "float16"
    except Exception:
        pass
    return "cpu", "int8"


@functools.lru_cache(maxsize=2)
def _load_model(size: str, device: str, compute_type: str):
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:  # pragma: no cover - depends on the environment
        # Show the real reason: it is often a blocked/missing DLL, not a missing package.
        raise RuntimeError(
            "faster-whisper could not be loaded: %s\n"
            "If it is genuinely missing run:  pip install -r requirements.txt\n"
            "If Windows says 'Application Control policy has blocked this file', "
            "use the Google Colab notebook (colab.ipynb) instead." % exc
        ) from exc
    return WhisperModel(size, device=device, compute_type=compute_type)


def read_wav_16k_mono(path):
    """Load a 16 kHz mono 16-bit WAV (as written by ``extract_audio``) as float32 samples."""
    import wave

    import numpy as np

    with wave.open(str(path), "rb") as w:
        if (w.getframerate(), w.getnchannels(), w.getsampwidth()) != (16000, 1, 2):
            raise ValueError("Expected a 16 kHz mono 16-bit WAV, got %s" % (w.getparams(),))
        raw = w.readframes(w.getnframes())
    return np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0


def _run(model, samples, language, song, initial_prompt, duration, progress) -> List[Line]:
    # NB: ``segments`` is a lazy generator, so GPU/CUDA errors only surface while
    # iterating it. The whole thing therefore has to live inside one function that
    # the caller can retry on the CPU.
    segments, _info = model.transcribe(
        samples,  # raw samples: avoids PyAV decoding
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
    return lines


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
    singing. If the GPU fails (e.g. ``libcublas.so.12 is not found``) the
    transcription is retried once on the CPU, which is slower but always works.
    """
    global _gpu_failed
    samples = read_wav_16k_mono(audio_path)

    device, compute_type = _pick_device()
    try:
        model = _load_model(model_size, device, compute_type)
        lines = _run(model, samples, language, song, initial_prompt, duration, progress)
    except Exception:
        if device == "cpu":
            raise
        _gpu_failed = True  # remember, and retry on the CPU
        model = _load_model(model_size, "cpu", "int8")
        lines = _run(model, samples, language, song, initial_prompt, duration, progress)

    if progress:
        progress(1.0)
    return normalize_lines(lines)
