"""End-to-end tests: real ffmpeg renders. Skipped automatically if ffmpeg is missing."""

import shutil
import subprocess
import tempfile
import unittest
from collections import Counter
from pathlib import Path

from captioner.models import Line, Word
from captioner.presets import PRESETS, StyleOptions
from captioner.render import RenderError, check_duration, probe, render_captions, VideoInfo

HAVE_FFMPEG = bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))

TELUGU = "నమస్కారం ప్రపంచం ఇది ఒక పరీక్ష"
HINDI = "नमस्ते दुनिया यह एक परीक्षण है"


def make_video(path, size="1280x720", seconds=8, audio=True):
    cmd = ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=0x203040:s=%s:d=%d:r=25" % (size, seconds)]
    if audio:
        cmd += ["-f", "lavfi", "-i", "sine=frequency=440:duration=%d" % seconds, "-c:a", "aac"]
    cmd += ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-shortest", str(path)]
    subprocess.run(cmd, check=True)
    return path


def frame_bytes(video, t):
    out = subprocess.run(
        ["ffmpeg", "-v", "error", "-ss", "%.3f" % t, "-i", str(video), "-frames:v", "1",
         "-f", "rawvideo", "-pix_fmt", "gray", "-"],
        capture_output=True, check=True,
    ).stdout
    return out


def has_caption_pixels(video, t, threshold=200):
    """The test background is one flat colour, so any other pixel is caption."""
    data = frame_bytes(video, t)
    common = Counter(data).most_common(1)[0][1]
    return (len(data) - common) > threshold


@unittest.skipUnless(HAVE_FFMPEG, "ffmpeg not installed")
class RenderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="captioner_test_"))
        cls.video = make_video(cls.tmp / "in.mp4")
        cls.lines = [
            Line.from_text("Hello brave new world", 1.0, 2.5),
            Line.from_text(TELUGU, 3.0, 5.0),
            Line.from_text(HINDI, 5.5, 7.5),
        ]

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_probe(self):
        info = probe(self.video)
        self.assertEqual((info.width, info.height), (1280, 720))
        self.assertAlmostEqual(info.duration, 8.0, delta=0.3)
        self.assertTrue(info.has_audio)

    def test_all_presets_render_with_audio_kept(self):
        for key in PRESETS:
            with self.subTest(preset=key):
                res = render_captions(self.video, self.lines, StyleOptions(preset=key), self.tmp / key)
                info = probe(res.video)
                self.assertAlmostEqual(info.duration, 8.0, delta=0.4)
                self.assertTrue(info.has_audio)
                self.assertEqual((info.width, info.height), (1280, 720))
                for f in (res.ass, res.srt, res.json):
                    self.assertTrue(f.exists() and f.stat().st_size > 0)
                self.assertFalse((self.tmp / key / "_work").exists())

    def test_captions_appear_only_while_line_is_active(self):
        for key in ("classic", "karaoke", "tiktok", "reveal", "boxed", "neon"):
            with self.subTest(preset=key):
                res = render_captions(self.video, self.lines[:1], StyleOptions(preset=key), self.tmp / ("sync_" + key))
                self.assertFalse(has_caption_pixels(res.video, 0.3), "caption before it is spoken")
                self.assertTrue(has_caption_pixels(res.video, 2.0), "caption missing during speech")
                self.assertFalse(has_caption_pixels(res.video, 4.0), "caption lingers after speech")

    def test_preview_window_keeps_sync(self):
        late = [Line.from_text("Late caption here", 5.0, 6.5)]
        res = render_captions(self.video, late, StyleOptions(preset="classic"), self.tmp / "prev", preview=True)
        info = probe(res.video)
        # window starts 0.5 s before the first caption (4.5 s) and the source ends at 8 s
        self.assertAlmostEqual(info.duration, 3.5, delta=0.4)
        self.assertFalse(has_caption_pixels(res.video, 0.1))  # source 4.6 s: not yet
        self.assertTrue(has_caption_pixels(res.video, 1.2))  # source 5.7 s: showing
        self.assertFalse(has_caption_pixels(res.video, 3.0))  # source 7.5 s: gone

    def test_portrait_and_odd_sizes(self):
        for size in ("720x1280", "641x361"):
            with self.subTest(size=size):
                src = make_video(self.tmp / ("v_%s.mp4" % size), size=size, seconds=3)
                lines = [Line.from_text("Portrait test line", 0.5, 2.5)]
                res = render_captions(src, lines, StyleOptions(preset="tiktok"), self.tmp / ("o_" + size))
                info = probe(res.video)
                self.assertEqual(info.width % 2, 0)
                self.assertEqual(info.height % 2, 0)
                self.assertTrue(has_caption_pixels(res.video, 1.5))

    def test_video_without_audio(self):
        src = make_video(self.tmp / "silent.mp4", seconds=3, audio=False)
        res = render_captions(src, [Line.from_text("no audio here", 0.5, 2.0)], StyleOptions(), self.tmp / "silent")
        self.assertFalse(probe(res.video).has_audio)

    def test_duration_limit(self):
        with self.assertRaises(ValueError):
            check_duration(VideoInfo(1280, 720, 125.0, True))
        check_duration(VideoInfo(1280, 720, 120.2, True))  # small tolerance
        check_duration(VideoInfo(1280, 720, 75.0, True))  # 2 minutes are allowed
        with self.assertRaises(ValueError):
            render_captions(self.video, self.lines, StyleOptions(), self.tmp / "lim", max_seconds=3)

    def test_empty_lines_rejected(self):
        with self.assertRaises(ValueError):
            render_captions(self.video, [], StyleOptions(), self.tmp / "empty")

    def test_missing_fonts_produce_warnings_not_errors(self):
        res = render_captions(self.video, self.lines, StyleOptions(preset="classic"), self.tmp / "warn")
        self.assertTrue(res.video.exists())  # warnings (if any) are informational

    def test_bad_input_file(self):
        bad = self.tmp / "bad.mp4"
        bad.write_text("not a video")
        with self.assertRaises(RenderError):
            render_captions(bad, self.lines, StyleOptions(), self.tmp / "bad")


if __name__ == "__main__":
    unittest.main()
