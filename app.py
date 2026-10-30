"""Web app:  python app.py   ->  http://127.0.0.1:7860

Flow: 1) upload + transcribe  2) fix any wrong words in the table
      3) pick a style, preview 6 seconds, then render the full video.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import gradio as gr

from captioner import fonts as fontlib
from captioner import previews
from captioner.models import lines_to_rows, rows_to_lines
from captioner.pipeline import transcribe_video
from captioner.presets import (COLOR_EFFECT_LABELS, COLOR_EFFECTS, EFFECTS, ENTRIES, POSITIONS,
                               PRESET_ORDER, PRESETS, StyleOptions)
from captioner.render import MAX_SECONDS, RenderError, render_captions
from captioner.transcribe import MODEL_SIZES

LANGUAGES = {
    "Telugu (తెలుగు)": "te",
    "Hindi (हिन्दी)": "hi",
    "English": "en",
    "Auto-detect": None,
}
CONTENT_TYPES = ["Speech / talking", "Song / music video"]
DEFAULT = "Preset default"


def _font_choices(script: str):
    """Fonts for a script; only the installed ones when we can tell (so a pick always works)."""
    names = fontlib.fonts_for(script)
    installed = [f for f in names if fontlib.font_available(f)]
    return [(DEFAULT, "")] + [(f, f) for f in (installed or names)]


def _safe_gallery(fn, *args):
    """Preview pictures are a nicety: never let a failure stop the app from starting."""
    try:
        return fn(*args)
    except Exception as exc:  # pragma: no cover
        print("[previews] skipped:", exc)
        return []


def _as_rows(table):
    if table is None:
        return []
    if hasattr(table, "values"):  # pandas DataFrame
        return table.values.tolist()
    return list(table)


# ---------------------------------------------------------------------------
# step 1: transcribe
# ---------------------------------------------------------------------------


def do_transcribe(video, language, content, model, max_words, hint, separate, progress=gr.Progress()):
    if not video:
        raise gr.Error("Please upload a video first.")
    try:
        lines, warnings = transcribe_video(
            video,
            language=LANGUAGES[language],
            model_size=model,
            song=(content == CONTENT_TYPES[1]),
            max_words=int(max_words),
            hint=(hint or "").strip() or None,
            separate_vocals=bool(separate),
            progress=lambda frac, msg: progress(frac, desc=msg),
        )
    except (ValueError, RuntimeError, RenderError) as exc:
        raise gr.Error(str(exc))
    msg = "Found %d caption lines. Fix any wrong words below, then choose a style." % len(lines)
    if warnings:
        msg += "\n\n" + "\n".join("⚠️ " + w for w in warnings)
    return lines_to_rows(lines), lines, msg


# ---------------------------------------------------------------------------
# step 2/3: render
# ---------------------------------------------------------------------------


def _render(video, table, originals, preset, anim, f_lat, f_te, f_hi, custom, c_base, c_hl, c_out,
            size, position, uppercase, spacing, effect, color_effect, preview):
    if not video:
        raise gr.Error("Please upload a video first.")
    lines = rows_to_lines(_as_rows(table), originals or [])
    if not lines:
        raise gr.Error("There are no captions yet. Click 'Transcribe' first (or type some lines in the table).")
    opts = StyleOptions(
        preset=preset,
        animation=anim or None,
        latin_font=f_lat or None,
        telugu_font=f_te or None,
        devanagari_font=f_hi or None,
        base_color=c_base if custom else None,
        highlight_color=c_hl if custom else None,
        outline_color=c_out if custom else None,
        size_scale=float(size),
        position=position or None,
        uppercase=True if uppercase else None,
        word_spacing=float(spacing),
        effect=effect or "none",
        color_effect=color_effect or "none",
    )
    try:
        res = render_captions(video, lines, opts, out_dir=tempfile.mkdtemp(prefix="captioner_out_"), preview=preview)
    except (ValueError, RuntimeError, RenderError) as exc:
        raise gr.Error(str(exc))
    msg = "Preview ready." if preview else "Done! Download the video and caption files below."
    if res.warnings:
        msg += "\n\n" + "\n".join("⚠️ " + w for w in res.warnings)
    return str(res.video), [str(res.video), str(res.srt), str(res.ass), str(res.json)], msg


def do_preview(*args):
    return _render(*args, preview=True)


def do_full(*args):
    return _render(*args, preview=False)


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------


def build_ui() -> gr.Blocks:
    with gr.Blocks(title="Video Captioner") as demo:
        gr.Markdown(
            "# 🎬 Video Captioner\n"
            "Free animated captions & lyrics for Telugu, Hindi and English videos "
            "(up to %d minutes), synced to the audio." % (MAX_SECONDS // 60)
        )
        originals = gr.State([])

        with gr.Row():
            with gr.Column(scale=1):
                gr.Markdown("### 1 · Upload & transcribe")
                video = gr.Video(label="Video", sources=["upload"], height=300)
                language = gr.Dropdown(list(LANGUAGES), value="Telugu (తెలుగు)", label="Language")
                content = gr.Radio(CONTENT_TYPES, value=CONTENT_TYPES[1], label="Content type")
                model = gr.Dropdown(MODEL_SIZES, value="small", label="Accuracy (bigger = better but slower)")
                max_words = gr.Slider(2, 10, value=5, step=1, label="Max words per caption line")
                with gr.Accordion("More options", open=False):
                    hint = gr.Textbox(label="Hint words (names, rare words) - optional")
                    separate = gr.Checkbox(
                        label="Remove background music first (needs the optional Demucs install)", value=False
                    )
                transcribe_btn = gr.Button("1 · Transcribe", variant="primary")
                status = gr.Markdown()

            with gr.Column(scale=1):
                gr.Markdown("### 2 · Fix the words")
                table = gr.Dataframe(
                    headers=["start (s)", "end (s)", "text"],
                    datatype=["number", "number", "str"],
                    col_count=(3, "fixed"),
                    row_count=(1, "dynamic"),
                    interactive=True,
                    wrap=True,
                    label="Edit the text of any line. Timing is kept.",
                )

        gr.Markdown("### 3 · Style")
        with gr.Row():
            preset = gr.Dropdown(
                [(PRESETS[k].label, k) for k in PRESET_ORDER], value="karaoke", label="Style preset"
            )
            anim = gr.Dropdown(
                [(DEFAULT, "")] + [(e.replace("_", " ").title(), e) for e in ENTRIES],
                value="", label="Entry animation",
            )
            position = gr.Dropdown(
                [(DEFAULT, "")] + [(p.title(), p) for p in POSITIONS], value="", label="Position"
            )
            size = gr.Slider(0.6, 1.8, value=1.0, step=0.05, label="Text size")
            spacing = gr.Slider(0.5, 3.0, value=1.0, step=0.1, label="Word spacing")
            uppercase = gr.Checkbox(label="UPPERCASE (English only)", value=False)
        with gr.Row():
            color_effect = gr.Dropdown(
                [(DEFAULT, "none")] + [(COLOR_EFFECT_LABELS.get(k, k), k) for k in COLOR_EFFECTS],
                value="none", label="Colourful text (rainbow, fire, gold...)",
            )
            effect = gr.Dropdown(
                [(e.title(), e) for e in EFFECTS], value="none", label="Motion effect (pulse, sway)"
            )
        with gr.Row():
            f_lat = gr.Dropdown(_font_choices("latin"), value="", label="English font")
            f_te = gr.Dropdown(_font_choices("telugu"), value="", label="Telugu font")
            f_hi = gr.Dropdown(_font_choices("devanagari"), value="", label="Hindi font")

        gr.Markdown("**Look before you choose** - click a picture to select it.")
        with gr.Tabs():
            with gr.Tab("Style presets"):
                pg = _safe_gallery(previews.preset_gallery)
                preset_keys = [k for _, _, k in pg]
                preset_gal = gr.Gallery(value=[(p, l) for p, l, _ in pg], columns=4, height=420,
                                        allow_preview=False, show_label=False)

                def pick_preset(evt: gr.SelectData):
                    return preset_keys[evt.index]

                preset_gal.select(pick_preset, None, preset)
            for title, script, target in (("English fonts", "latin", f_lat), ("Telugu fonts", "telugu", f_te),
                                          ("Hindi fonts", "devanagari", f_hi)):
                with gr.Tab(title):
                    fg = _safe_gallery(previews.font_gallery, script)
                    names = [fam for _, fam in fg]
                    gal = gr.Gallery(value=[(p, f) for p, f in fg], columns=3, height=460,
                                     allow_preview=False, show_label=False)

                    def pick_font(evt: gr.SelectData, names=names):
                        return names[evt.index]

                    gal.select(pick_font, None, target)
        with gr.Row():
            custom = gr.Checkbox(label="Use custom colours", value=False)
            c_base = gr.ColorPicker(value="#FFFFFF", label="Text")
            c_hl = gr.ColorPicker(value="#FFD400", label="Highlight")
            c_out = gr.ColorPicker(value="#000000", label="Outline")

        with gr.Row():
            preview_btn = gr.Button("Preview (6 s)")
            render_btn = gr.Button("3 · Render full video", variant="primary")
        out_video = gr.Video(label="Result", height=420)
        downloads = gr.File(label="Downloads (video, .srt, .ass, editable .json)", file_count="multiple")
        out_status = gr.Markdown()

        transcribe_btn.click(
            do_transcribe,
            inputs=[video, language, content, model, max_words, hint, separate],
            outputs=[table, originals, status],
        )
        style_inputs = [video, table, originals, preset, anim, f_lat, f_te, f_hi,
                        custom, c_base, c_hl, c_out, size, position, uppercase, spacing, effect, color_effect]
        preview_btn.click(do_preview, inputs=style_inputs, outputs=[out_video, downloads, out_status])
        render_btn.click(do_full, inputs=style_inputs, outputs=[out_video, downloads, out_status])
    return demo


def main() -> None:
    # Fetch the free fonts on first run (needs internet; skipped quietly if offline).
    try:
        fontlib.download_missing(log=lambda m: print("[fonts]", m))
    except Exception as exc:  # pragma: no cover
        print("[fonts] skipped:", exc)
    demo = build_ui()
    demo.queue().launch(
        server_name=os.environ.get("GRADIO_SERVER_NAME", "127.0.0.1"),
        server_port=int(os.environ.get("GRADIO_SERVER_PORT", "7860")),
        share=os.environ.get("GRADIO_SHARE") == "1",  # public link, used by the Colab notebook
    )


if __name__ == "__main__":
    main()
