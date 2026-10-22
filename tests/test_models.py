import json
import tempfile
import unittest
from pathlib import Path

from captioner.models import (
    Line,
    Word,
    chunk_lines,
    lines_to_rows,
    load_lines,
    normalize_lines,
    rows_to_lines,
    save_lines,
    to_srt,
)
from captioner.presets import StyleOptions, normalize_color, resolve_style
from captioner.scripts import script_of

TELUGU = "నమస్కారం ప్రపంచం ఇది ఒక పరీక్ష"
HINDI = "नमस्ते दुनिया यह एक परीक्षण है"


def make_line(text="one two three four", start=1.0, end=3.0):
    return Line.from_text(text, start, end)


class ScriptTests(unittest.TestCase):
    def test_script_detection(self):
        self.assertEqual(script_of("నమస్కారం"), "telugu")
        self.assertEqual(script_of("नमस्ते"), "devanagari")
        self.assertEqual(script_of("hello"), "latin")
        self.assertEqual(script_of("123,"), "latin")


class LineTests(unittest.TestCase):
    def test_from_text_is_contiguous_and_bounded(self):
        line = make_line()
        self.assertAlmostEqual(line.start, 1.0)
        self.assertAlmostEqual(line.end, 3.0)
        for a, b in zip(line.words, line.words[1:]):
            self.assertAlmostEqual(a.end, b.start)

    def test_with_text_same_word_count_keeps_timing(self):
        line = Line([Word("a", 1.0, 1.4), Word("b", 1.6, 2.0), Word("c", 2.5, 3.0)])
        new = line.with_text("x y z")
        self.assertEqual([w.text for w in new.words], ["x", "y", "z"])
        self.assertEqual([(w.start, w.end) for w in new.words], [(1.0, 1.4), (1.6, 2.0), (2.5, 3.0)])

    def test_with_text_new_bounds_rescales(self):
        line = Line([Word("a", 0.0, 1.0), Word("b", 1.0, 2.0)])
        new = line.with_text("a b", 10.0, 14.0)
        self.assertAlmostEqual(new.words[0].start, 10.0)
        self.assertAlmostEqual(new.words[1].start, 12.0)
        self.assertAlmostEqual(new.end, 14.0)

    def test_with_text_different_word_count_spreads(self):
        line = make_line("one two", 0.0, 2.0)
        new = line.with_text("one two three four five")
        self.assertEqual(len(new.words), 5)
        self.assertAlmostEqual(new.start, 0.0)
        self.assertAlmostEqual(new.end, 2.0)

    def test_empty_text_returns_none(self):
        self.assertIsNone(make_line().with_text("   "))
        self.assertIsNone(Line.from_text("", 0, 1))

    def test_telugu_weights_ignore_combining_marks(self):
        line = Line.from_text(TELUGU, 0.0, 5.0)
        self.assertEqual(len(line.words), 5)
        self.assertAlmostEqual(line.end, 5.0)
        # "ఇది" (2 letters + vowel sign) must get a shorter slot than "ప్రపంచం"
        by_text = {w.text: w.end - w.start for w in line.words}
        self.assertLess(by_text["ఇది"], by_text["ప్రపంచం"])


class ChunkTests(unittest.TestCase):
    def test_balanced_split(self):
        line = make_line("a b c d e f g", 0, 7)
        parts = chunk_lines([line], max_words=3, max_seconds=100)
        self.assertEqual([len(p.words) for p in parts], [3, 2, 2])

    def test_split_at_silence(self):
        words = [Word("a", 0, 0.5), Word("b", 0.5, 1.0), Word("c", 6.0, 6.5)]
        parts = chunk_lines([Line(words)], max_words=10, max_seconds=100, max_gap=1.0)
        self.assertEqual([[w.text for w in p.words] for p in parts], [["a", "b"], ["c"]])

    def test_split_by_duration(self):
        line = make_line("a b c d", 0, 20)
        parts = chunk_lines([line], max_words=10, max_seconds=5)
        self.assertEqual(len(parts), 4)


class EditingTests(unittest.TestCase):
    def setUp(self):
        self.lines = [make_line("hello world", 0.0, 2.0), make_line("second line here", 2.5, 5.0)]

    def test_roundtrip_unchanged(self):
        rows = lines_to_rows(self.lines)
        back = rows_to_lines(rows, self.lines)
        self.assertEqual([l.text for l in back], [l.text for l in self.lines])
        for a, b in zip(back, self.lines):
            self.assertAlmostEqual(a.start, b.start, places=6)
            self.assertAlmostEqual(a.words[0].end, b.words[0].end, places=6)

    def test_typo_fix_keeps_word_timing(self):
        rows = lines_to_rows(self.lines)
        rows[0][2] = "hullo world"
        back = rows_to_lines(rows, self.lines)
        self.assertEqual(back[0].words[0].text, "hullo")
        self.assertAlmostEqual(back[0].words[0].end, self.lines[0].words[0].end, places=6)

    def test_deleted_and_added_rows(self):
        rows = lines_to_rows(self.lines)
        rows.pop(0)
        rows.append([6.0, 8.0, "brand new"])
        back = rows_to_lines(rows, self.lines)
        self.assertEqual([l.text for l in back], ["second line here", "brand new"])

    def test_blank_and_nan_rows_dropped(self):
        rows = [[0.0, 1.0, ""], [float("nan"), 1.0, "x"], [1.0, 2.0, "ok"], [None, None, None]]
        back = rows_to_lines(rows, [])
        self.assertEqual([l.text for l in back], ["ok"])

    def test_normalize_orders_and_fixes_durations(self):
        bad = [Line([Word("b", 5, 5)]), Line([Word("a", 1, 0.5), Word("c", 0.2, 0.3)])]
        out = normalize_lines(bad)
        self.assertEqual([l.text for l in out], ["a c", "b"])
        for l in out:
            for w in l.words:
                self.assertGreater(w.end, w.start)


class SerialisationTests(unittest.TestCase):
    def test_json_roundtrip_unicode(self):
        lines = [Line.from_text(TELUGU, 0, 4), Line.from_text(HINDI, 4, 8)]
        with tempfile.TemporaryDirectory() as d:
            p = save_lines(lines, Path(d) / "c.json")
            self.assertIn("నమస్కారం", p.read_text(encoding="utf-8"))  # not \u-escaped
            back = load_lines(p)
        self.assertEqual([l.text for l in back], [l.text for l in lines])

    def test_srt(self):
        srt = to_srt([Line.from_text("hi there", 1.5, 62.25)])
        self.assertIn("1\n00:00:01,500 --> 00:01:02,250\nhi there\n", srt)


class StyleTests(unittest.TestCase):
    def test_colors(self):
        self.assertEqual(normalize_color("#abc"), "#AABBCC")
        self.assertEqual(normalize_color("rgba(255, 128, 0, 1)"), "#FF8000")
        self.assertIsNone(normalize_color(""))
        with self.assertRaises(ValueError):
            normalize_color("banana")

    def test_overrides(self):
        s = resolve_style(StyleOptions(preset="classic", animation="slide_up", latin_font="Anton",
                                       base_color="#ff0000", size_scale=2.0, position="top", uppercase=True))
        self.assertEqual((s.entry, s.latin_font, s.base_color, s.position, s.uppercase),
                         ("slide_up", "Anton", "#FF0000", "top", True))
        self.assertAlmostEqual(s.size, 0.12)

    def test_pop_falls_back_for_word_modes(self):
        s = resolve_style(StyleOptions(preset="tiktok", animation="pop"))
        self.assertEqual(s.entry, "fade")

    def test_unknown_preset(self):
        with self.assertRaises(ValueError):
            resolve_style(StyleOptions(preset="nope"))


if __name__ == "__main__":
    unittest.main()
