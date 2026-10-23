import re
import unittest

from captioner.ass import ass_time, build_ass, style_color, tag_color
from captioner.models import Line, Word
from captioner.presets import PRESETS, StyleOptions, resolve_style

TELUGU = "నమస్కారం ప్రపంచం ఇది ఒక పరీక్ష"
HINDI = "नमस्ते दुनिया यह एक परीक्षण है"


def build(preset, lines, w=1280, h=720, **opts):
    return build_ass(lines, w, h, resolve_style(StyleOptions(preset=preset, **opts)))


def events(ass):
    return [l for l in ass.splitlines() if l.startswith("Dialogue:")]


def secs(t):
    h, m, s = t.split(":")
    return int(h) * 3600 + int(m) * 60 + float(s)


def times(ev):
    parts = ev.split(",", 3)
    return secs(parts[1]), secs(parts[2])


class HelperTests(unittest.TestCase):
    def test_time_format(self):
        self.assertEqual(ass_time(0), "0:00:00.00")
        self.assertEqual(ass_time(61.234), "0:01:01.23")
        self.assertEqual(ass_time(3661.999), "1:01:02.00")

    def test_colours_are_bgr(self):
        self.assertEqual(style_color("#FF8000"), "&H000080FF")
        self.assertEqual(style_color("#000000", 0x66), "&H66000000")
        self.assertEqual(tag_color("#FF8000"), "&H0080FF&")


class StructureTests(unittest.TestCase):
    def setUp(self):
        self.lines = [
            Line.from_text("Hello brave new world", 1.0, 3.0),
            Line.from_text(TELUGU, 3.5, 6.0),
            Line.from_text(HINDI, 6.5, 9.0),
            Line.from_text("mixed హలో नमस्ते words", 9.5, 11.0),
        ]

    def test_every_preset_builds_with_valid_events(self):
        for key in PRESETS:
            with self.subTest(preset=key):
                ass = build(key, self.lines)
                self.assertIn("[V4+ Styles]", ass)
                self.assertIn("PlayResX: 1280", ass)
                evs = events(ass)
                self.assertGreaterEqual(len(evs), len(self.lines))
                for ev in evs:
                    s, e = times(ev)
                    self.assertLess(s, e, ev)
                    self.assertEqual(ev.count("{"), ev.count("}"), ev)
                    self.assertEqual(len(ev.split(",", 9)), 10, ev)  # 9 fixed fields + text

    def test_no_overlap_between_lines(self):
        for key in PRESETS:
            with self.subTest(preset=key):
                # Word-mode events tile a line and glow layers duplicate spans, so
                # the set of distinct spans must never overlap (libass would stack them).
                spans = sorted(set(times(e) for e in events(build(key, self.lines))))
                for (s1, e1), (s2, e2) in zip(spans, spans[1:]):
                    self.assertGreaterEqual(s2, e1 - 0.011, (key, (s1, e1), (s2, e2)))

    def test_karaoke_durations_cover_the_line(self):
        ass = build("karaoke", [Line.from_text("a b c", 2.0, 5.0)])
        (ev,) = events(ass)
        s, e = times(ev)
        total_cs = sum(int(x) for x in re.findall(r"\\k(?:f)?(\d+)", ev))
        # lead + all word sweeps == time from event start to the end of the last word
        self.assertAlmostEqual(total_cs / 100.0, 5.0 - s, delta=0.03)
        self.assertGreaterEqual(e, 5.0)

    def test_karaoke_first_word_starts_at_its_audio_time(self):
        ass = build("karaoke", [Line([Word("a", 4.0, 4.5), Word("b", 4.5, 5.0)])])
        (ev,) = events(ass)
        s, _ = times(ev)
        lead = int(re.search(r"\\k(\d+)\}", ev).group(1))
        self.assertAlmostEqual(s + lead / 100.0, 4.0, delta=0.02)

    def test_word_highlight_one_event_per_word(self):
        ass = build("tiktok", [Line.from_text("one two three", 1.0, 4.0)])
        evs = events(ass)
        self.assertGreaterEqual(len(evs), 3)
        highlighted = [e for e in evs if "\\fscx112" in e]
        self.assertEqual(len(highlighted), 3)
        # events tile the line without gaps/overlaps
        spans = sorted(times(e) for e in evs)
        for (s1, e1), (s2, e2) in zip(spans, spans[1:]):
            self.assertAlmostEqual(e1, s2, delta=0.011)

    def test_word_reveal_hides_future_words(self):
        ass = build("reveal", [Line.from_text("one two three", 1.0, 4.0)])
        evs = events(ass)
        self.assertEqual(len(evs), 3)
        self.assertEqual(evs[0].count("\\alpha&HFF&"), 3)  # first word animates from hidden + 2 hidden
        self.assertEqual(evs[2].count("\\alpha&HFF&"), 1)  # last word is animating in

    def test_font_switches_per_script(self):
        ass = build("classic", [Line.from_text("hello హలో नमस्ते", 1, 3)])
        (ev,) = events(ass)
        self.assertIn("\\fnMandali", ev)
        self.assertIn("\\fnHind", ev)

    def test_font_overrides(self):
        ass = build("classic", [Line.from_text(TELUGU, 1, 3)], telugu_font="NTR")
        self.assertIn("\\fnNTR", ass)

    def test_slide_up_and_pop_tags(self):
        self.assertIn("\\move(", build("slideup", [Line.from_text("hi there", 1, 3)]))
        pop = build("pop", [Line.from_text("hi there", 1, 3)])
        self.assertIn("\\fscx0", pop)
        self.assertIn("\\t(0,150", pop)

    def test_glow_adds_a_second_layer(self):
        ass = build("neon", [Line.from_text("hi there", 1, 3)])
        layers = sorted(e.split(",")[0] for e in events(ass))
        self.assertEqual(layers, ["Dialogue: 0", "Dialogue: 1"])

    def test_uppercase_only_affects_latin(self):
        ass = build("classic", [Line.from_text("hello " + TELUGU.split()[0], 1, 3)], uppercase=True)
        self.assertIn("HELLO", ass)
        self.assertIn(TELUGU.split()[0], ass)

    def test_text_is_escaped(self):
        ass = build("classic", [Line.from_text(r"evil {\fs999} \N text", 1, 3)])
        (ev,) = events(ass)
        body = ev.split(",", 9)[9]
        self.assertNotIn("\\fs999", body)
        self.assertEqual(body.count("{"), body.count("}"))

    def test_position_and_size_scale_with_resolution(self):
        small = build("classic", [Line.from_text("hi", 1, 2)], 640, 360)
        big = build("classic", [Line.from_text("hi", 1, 2)], 1920, 1080)
        fs = lambda a: int(re.search(r"Style: Cap,[^,]+,(\d+),", a).group(1))
        self.assertAlmostEqual(fs(big) / fs(small), 3.0, delta=0.15)
        portrait = build("classic", [Line.from_text("hi", 1, 2)], 720, 1280)
        self.assertIn("\\pos(360,", events(portrait)[0])

    def test_empty_input(self):
        ass = build("karaoke", [])
        self.assertEqual(events(ass), [])


if __name__ == "__main__":
    unittest.main()


class StyleVarietyTests(unittest.TestCase):
    LINES = [Line.from_text("hello brave new world", 1.0, 3.0), Line.from_text(TELUGU, 3.5, 5.5)]

    def test_every_entry_animation_with_every_mode(self):
        from captioner.presets import ENTRIES

        for preset in ("classic", "karaoke", "tiktok", "reveal"):
            for entry in ENTRIES:
                with self.subTest(preset=preset, entry=entry):
                    ass = build(preset, self.LINES, animation=entry)
                    evs = events(ass)
                    self.assertGreaterEqual(len(evs), 2)
                    for ev in evs:
                        s, e = times(ev)
                        self.assertLess(s, e)
                        self.assertEqual(ev.count("{"), ev.count("}"), ev)

    def test_new_entry_tags(self):
        one = [Line.from_text("hello there", 1.0, 3.0)]
        self.assertIn("\\fry90", build("classic", one, animation="flip"))
        self.assertIn("\\frz-8", build("classic", one, animation="wobble"))
        self.assertIn("\\fscx140", build("classic", one, animation="zoom"))
        self.assertIn("\\blur12", build("classic", one, animation="blur_in"))
        for entry in ("drop", "slide_left", "slide_right", "slide_up"):
            self.assertIn("\\move(", build("classic", one, animation=entry))
        # entering from the left starts left of the final x position
        ev = events(build("classic", one, animation="slide_left"))[0]
        x0, _, x1 = [int(v) for v in re.search(r"\\move\((-?\d+),(\d+),(-?\d+)", ev).groups()]
        self.assertLess(x0, x1)

    def test_scale_entries_fall_back_in_word_modes(self):
        for entry in ("pop", "zoom"):
            self.assertEqual(resolve_style(StyleOptions(preset="tiktok", animation=entry)).entry, "fade")
        self.assertEqual(resolve_style(StyleOptions(preset="tiktok", animation="flip")).entry, "flip")

    def test_blur_in_ends_at_the_preset_blur(self):
        ev = events(build("neon", [Line.from_text("hi there", 1, 3)], animation="blur_in"))
        self.assertTrue(any("\\t(0," in e and "\\blur0.8)" in e for e in ev))

    def test_narrow_space_scripts_get_wider_gaps(self):
        # with no font files installed the per-script defaults apply: Telugu/Hindi are narrow
        te = events(build("classic", [Line.from_text(TELUGU, 1, 3)]))[0]
        self.assertIn("\\fsp", te)
        latin = events(build("classic", [Line.from_text("hello brave new world", 1, 3)]))[0]
        self.assertNotIn("\\fsp", latin)

    def test_word_spacing_option(self):
        one = [Line.from_text("hello brave new world", 1, 3)]
        wider = events(build("classic", one, word_spacing=2.0))[0]
        self.assertIn("\\fsp", wider)
        def gap(ass):
            return float(re.search(r"\\fsp(\d+\.\d)\}", events(ass)[0]).group(1))
        self.assertGreater(gap(build("classic", one, word_spacing=3.0)), gap(build("classic", one, word_spacing=2.0)))

    def test_gap_resets_to_style_spacing_and_keeps_karaoke_timing(self):
        ev = events(build("karaoke", [Line.from_text(TELUGU, 2.0, 7.0)]))[0]
        self.assertRegex(ev, r"\{\\fsp[\d.]+\} \{\\fsp0\.0\}")
        s, e = times(ev)
        total_cs = sum(int(x) for x in re.findall(r"\\k(?:f)?(\d+)", ev))
        self.assertAlmostEqual(total_cs / 100.0, 7.0 - s, delta=0.05)

    def test_new_presets_exist_and_use_registered_fonts(self):
        from captioner.fonts import FONTS

        for key in ("comic", "marker", "elegant", "impact", "dream"):
            pr = PRESETS[key]
            for fam in (pr.latin_font, pr.telugu_font, pr.devanagari_font):
                self.assertIn(fam, FONTS, (key, fam))

    def test_font_registry_is_consistent(self):
        from captioner.fonts import FONTS, fonts_for

        self.assertGreaterEqual(len(fonts_for("telugu")), 15)
        for fam, spec in FONTS.items():
            self.assertTrue(spec.files and spec.scripts, fam)
            for f in spec.files:
                self.assertTrue(f.endswith(".ttf"), f)
            if spec.has_bold:
                self.assertTrue(any("Bold" in f for f in spec.files), fam)
