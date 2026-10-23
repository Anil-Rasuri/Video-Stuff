import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from captioner.render import extract_audio
from captioner.transcribe import read_wav_16k_mono

HAVE_FFMPEG = bool(shutil.which("ffmpeg"))


@unittest.skipUnless(HAVE_FFMPEG, "ffmpeg not installed")
class AudioLoadTests(unittest.TestCase):
    def test_extracted_audio_loads_as_float_samples(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            src = d / "in.mp4"
            subprocess.run(
                ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
                 "-f", "lavfi", "-i", "color=c=black:s=64x64:d=2", "-shortest", str(src)],
                check=True,
            )
            wav = extract_audio(src, d / "a.wav")
            samples = read_wav_16k_mono(wav)
            self.assertEqual(str(samples.dtype), "float32")
            self.assertAlmostEqual(len(samples) / 16000.0, 2.0, delta=0.15)
            self.assertGreater(float(abs(samples).max()), 0.1)
            self.assertLessEqual(float(abs(samples).max()), 1.0)

    def test_wrong_format_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            wav = Path(d) / "stereo.wav"
            subprocess.run(
                ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "sine=duration=1", "-ac", "2",
                 "-ar", "44100", str(wav)],
                check=True,
            )
            with self.assertRaises(ValueError):
                read_wav_16k_mono(wav)

    def test_audio_from_any_audio_file_can_be_normalised(self):
        # same call the Demucs step uses: audio file in, 16 kHz mono WAV out
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            stereo = d / "stereo.wav"
            subprocess.run(
                ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "sine=duration=1", "-ac", "2",
                 "-ar", "44100", str(stereo)],
                check=True,
            )
            samples = read_wav_16k_mono(extract_audio(stereo, d / "n.wav"))
            self.assertAlmostEqual(len(samples) / 16000.0, 1.0, delta=0.1)


if __name__ == "__main__":
    unittest.main()
