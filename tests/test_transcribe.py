"""Transcription logic with a fake faster-whisper (no model download needed)."""

import os
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path

from captioner import transcribe as tr
from captioner.render import extract_audio


class _W:
    def __init__(self, word, start, end):
        self.word, self.start, self.end = word, start, end


class _Seg:
    def __init__(self, text, start, end, words=None):
        self.text, self.start, self.end, self.words = text, start, end, words


def make_fake_module(log, gpu_breaks):
    class WhisperModel:
        def __init__(self, size, device="cpu", compute_type="int8"):
            self.device = device
            log.append(("load", size, device))

        def transcribe(self, audio, **kw):
            log.append(("transcribe", self.device, type(audio).__name__, kw["language"], kw["vad_filter"]))

            def gen():
                if self.device == "cuda" and gpu_breaks:
                    raise RuntimeError("Library libcublas.so.12 is not found or cannot be loaded")
                yield _Seg("hello world", 0.0, 1.0, [_W(" hello", 0.0, 0.5), _W(" world", 0.5, 1.0)])
                yield _Seg("no word timing here", 1.5, 3.0, None)

            return gen(), object()

    mod = types.ModuleType("faster_whisper")
    mod.WhisperModel = WhisperModel
    return mod


@unittest.skipUnless(shutil.which("ffmpeg"), "ffmpeg not installed")
class TranscribeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        src = self.tmp / "in.mp4"
        subprocess.run(
            ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "sine=duration=3", "-f", "lavfi",
             "-i", "color=c=black:s=64x64:d=3", "-shortest", str(src)], check=True)
        self.wav = extract_audio(src, self.tmp / "a.wav")
        self._saved = sys.modules.get("faster_whisper")
        self._env = os.environ.get("CAPTIONER_DEVICE")
        tr._load_model.cache_clear()
        tr._gpu_failed = False

    def tearDown(self):
        if self._saved is None:
            sys.modules.pop("faster_whisper", None)
        else:
            sys.modules["faster_whisper"] = self._saved
        if self._env is None:
            os.environ.pop("CAPTIONER_DEVICE", None)
        else:
            os.environ["CAPTIONER_DEVICE"] = self._env
        tr._load_model.cache_clear()
        tr._gpu_failed = False
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_segments_become_lines_and_samples_are_passed(self):
        log = []
        sys.modules["faster_whisper"] = make_fake_module(log, gpu_breaks=False)
        os.environ["CAPTIONER_DEVICE"] = "cpu"
        lines = tr.transcribe_audio(self.wav, language="te", song=True)
        self.assertEqual([l.text for l in lines], ["hello world", "no word timing here"])
        self.assertEqual(lines[0].words[0].text, "hello")  # stripped
        self.assertEqual(len(lines[1].words), 4)  # spread across the segment
        self.assertIn(("transcribe", "cpu", "ndarray", "te", False), log)  # array in, vad off for songs

    def test_gpu_failure_at_iteration_time_falls_back_to_cpu(self):
        log = []
        sys.modules["faster_whisper"] = make_fake_module(log, gpu_breaks=True)
        os.environ["CAPTIONER_DEVICE"] = "cuda"  # pretend a GPU exists
        lines = tr.transcribe_audio(self.wav, language="en")
        self.assertEqual(len(lines), 2)
        self.assertEqual([e[2] for e in log if e[0] == "load"], ["cuda", "cpu"])
        self.assertTrue(tr._gpu_failed)
        # the next call goes straight to the CPU without touching the GPU again
        log.clear()
        tr.transcribe_audio(self.wav, language="en")
        self.assertEqual([e[2] for e in log if e[0] == "load"], [])  # cached CPU model
        self.assertTrue(all(e[1] == "cpu" for e in log if e[0] == "transcribe"))

    def test_cpu_errors_are_not_swallowed(self):
        class Boom:
            def __init__(self, *a, **k): pass
            def transcribe(self, *a, **k): raise RuntimeError("real problem")
        mod = types.ModuleType("faster_whisper"); mod.WhisperModel = Boom
        sys.modules["faster_whisper"] = mod
        os.environ["CAPTIONER_DEVICE"] = "cpu"
        with self.assertRaisesRegex(RuntimeError, "real problem"):
            tr.transcribe_audio(self.wav)

    def test_progress_reaches_one(self):
        sys.modules["faster_whisper"] = make_fake_module([], gpu_breaks=False)
        os.environ["CAPTIONER_DEVICE"] = "cpu"
        seen = []
        tr.transcribe_audio(self.wav, duration=3.0, progress=seen.append)
        self.assertEqual(seen[-1], 1.0)
        self.assertEqual(seen, sorted(seen))


if __name__ == "__main__":
    unittest.main()


class BlockedAvTests(unittest.TestCase):
    """If PyAV cannot be imported (blocked DLL), faster-whisper must still load."""

    def test_import_survives_a_broken_av(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            (tmp / "av").mkdir()
            (tmp / "av" / "__init__.py").write_text(
                "raise ImportError('DLL load failed while importing frame: An Application Control policy has blocked this file.')\n")
            (tmp / "faster_whisper").mkdir()
            (tmp / "faster_whisper" / "__init__.py").write_text(
                "import av\nclass WhisperModel:\n    pass\n")
            saved = {k: sys.modules.pop(k) for k in list(sys.modules) if k == "av" or k.startswith(("av.", "faster_whisper"))}
            sys.path.insert(0, str(tmp))
            try:
                model_cls = tr._import_whisper_model()
                self.assertEqual(model_cls.__name__, "WhisperModel")
                with self.assertRaises(RuntimeError):
                    sys.modules["av"].anything  # the stub fails loudly if PyAV is ever really needed
            finally:
                sys.path.remove(str(tmp))
                for k in [k for k in sys.modules if k == "av" or k.startswith(("av.", "faster_whisper"))]:
                    del sys.modules[k]
                sys.modules.update(saved)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_unrelated_import_errors_are_reported(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            (tmp / "faster_whisper").mkdir()
            (tmp / "faster_whisper" / "__init__.py").write_text("import definitely_not_installed_pkg\n")
            saved = {k: sys.modules.pop(k) for k in list(sys.modules) if k == "av" or k.startswith(("av.", "faster_whisper"))}
            sys.path.insert(0, str(tmp))
            try:
                with self.assertRaisesRegex(RuntimeError, "could not be loaded"):
                    tr._import_whisper_model()
            finally:
                sys.path.remove(str(tmp))
                for k in [k for k in sys.modules if k == "av" or k.startswith(("av.", "faster_whisper"))]:
                    del sys.modules[k]
                sys.modules.update(saved)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
