"""Command line interface:  python -m captioner <command> ..."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import fonts as fontlib
from .models import load_lines, save_lines
from .presets import ENTRIES, POSITIONS, PRESETS, StyleOptions

LANG_CHOICES = ["auto", "te", "hi", "en"]


def _add_transcribe_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("-l", "--lang", choices=LANG_CHOICES, default="auto", help="spoken/sung language")
    p.add_argument(
        "-m",
        "--model",
        default="small",
        help="Whisper model: tiny, base, small, medium, large-v3-turbo, large-v3 (default: small)",
    )
    p.add_argument("--song", action="store_true", help="music video: disable the speech-only filter")
    p.add_argument("--separate-vocals", action="store_true", help="remove music first (needs Demucs)")
    p.add_argument("--max-words", type=int, default=5, help="max words per caption line (default 5)")
    p.add_argument("--hint", default=None, help="optional words/names to help recognition")


def _add_style_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("-p", "--preset", choices=list(PRESETS), default="karaoke")
    p.add_argument("-a", "--animation", choices=list(ENTRIES), default=None, help="override entry animation")
    p.add_argument("--latin-font", default=None)
    p.add_argument("--telugu-font", default=None)
    p.add_argument("--hindi-font", default=None, dest="devanagari_font")
    p.add_argument("--color", default=None, help="text colour, e.g. #FFFFFF")
    p.add_argument("--highlight", default=None, help="highlight colour, e.g. #FFD400")
    p.add_argument("--outline", default=None, help="outline colour, e.g. #000000")
    p.add_argument("--size", type=float, default=1.0, help="font size multiplier (default 1.0)")
    p.add_argument("--position", choices=list(POSITIONS), default=None)
    p.add_argument("--uppercase", action="store_true", default=None)
    p.add_argument("--word-spacing", type=float, default=1.0, help="gap between words, 1.0 = normal (try 1.5)")
    p.add_argument("--preview", action="store_true", help="render only ~6 seconds to check the look")


def _options(args) -> StyleOptions:
    return StyleOptions(
        preset=args.preset,
        animation=args.animation,
        latin_font=args.latin_font,
        telugu_font=args.telugu_font,
        devanagari_font=args.devanagari_font,
        base_color=args.color,
        highlight_color=args.highlight,
        outline_color=args.outline,
        size_scale=args.size,
        position=args.position,
        uppercase=args.uppercase,
        word_spacing=args.word_spacing,
    )


def _transcribe(args):
    from .pipeline import transcribe_video

    def show(frac, msg):
        print("\r[%3d%%] %-45s" % (int(frac * 100), msg), end="", file=sys.stderr, flush=True)

    lines, warnings = transcribe_video(
        args.video,
        language=None if args.lang == "auto" else args.lang,
        model_size=args.model,
        song=args.song,
        max_words=args.max_words,
        hint=args.hint,
        separate_vocals=args.separate_vocals,
        progress=show,
    )
    print(file=sys.stderr)
    for w in warnings:
        print("warning:", w, file=sys.stderr)
    return lines


def _render(args, lines):
    from .render import render_captions

    out_dir = Path(args.out) if getattr(args, "out", None) else Path(args.video).resolve().parent
    res = render_captions(args.video, lines, _options(args), out_dir=out_dir, preview=args.preview)
    for w in res.warnings:
        print("warning:", w, file=sys.stderr)
    print("video:", res.video)
    print("srt:  ", res.srt)
    print("ass:  ", res.ass)


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(
        prog="captioner", description="Free animated captions / lyrics for short videos."
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("run", help="transcribe and render in one go")
    p.add_argument("video")
    p.add_argument("-o", "--out", help="output folder (default: next to the video)")
    _add_transcribe_args(p)
    _add_style_args(p)

    p = sub.add_parser("transcribe", help="write an editable captions.json (fix typos, then 'render')")
    p.add_argument("video")
    p.add_argument("-o", "--out", help="captions file (default: <video>.captions.json)")
    _add_transcribe_args(p)

    p = sub.add_parser("render", help="render a video from an (edited) captions.json")
    p.add_argument("video")
    p.add_argument("captions", help="captions.json from the 'transcribe' command")
    p.add_argument("-o", "--out", help="output folder (default: next to the video)")
    _add_style_args(p)

    p = sub.add_parser("fonts", help="download the free fonts (Telugu / Hindi / English)")
    p.add_argument("--list", action="store_true", help="only show what is installed")
    p.add_argument("--force", action="store_true", help="re-download existing files")

    sub.add_parser("presets", help="list the style presets")

    args = parser.parse_args(argv)

    try:
        if args.cmd == "run":
            _render(args, _transcribe(args))
        elif args.cmd == "transcribe":
            lines = _transcribe(args)
            out = Path(args.out) if args.out else Path(args.video).with_suffix(".captions.json")
            save_lines(lines, out)
            print("Wrote %s  (%d lines). Edit the text if needed, then run 'render'." % (out, len(lines)))
        elif args.cmd == "render":
            _render(args, load_lines(args.captions))
        elif args.cmd == "fonts":
            if args.list:
                for fam, spec in fontlib.FONTS.items():
                    state = "installed" if fontlib.font_available(fam) else "missing"
                    print("%-12s %-10s %s" % (fam, "/".join(spec.scripts), state))
            else:
                res = fontlib.download_fonts(force=args.force)
                bad = [f for f, ok in res.items() if not ok]
                print("Done." if not bad else "Some fonts failed: " + ", ".join(bad))
        elif args.cmd == "presets":
            for key, pr in PRESETS.items():
                print("%-9s %-34s %s" % (key, pr.label, pr.description))
    except (ValueError, RuntimeError) as exc:
        print("error:", exc, file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
