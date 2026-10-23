# 🎬 Video Captioner

Free, open-source **animated captions and lyrics** for short videos (up to 60 seconds) in **Telugu, Hindi and English**. Upload a video, get word-accurate text, fix any mistakes, pick a style, and download the video with captions burned in, synced to the audio.

- **Speech/lyrics → text** with [faster-whisper](https://github.com/SYSTRAN/faster-whisper) (Whisper), running locally. No API keys, no cost.
- **Word-level timing**, so words highlight exactly when they are spoken or sung.
- **13 animated styles** and **11 entry animations** (fade, pop, zoom, blur-in, wobble, flip, drop, slide up/left/right...), mix and match.
- **Free fonts for all three scripts** (Google Fonts, SIL OFL), chosen automatically per word, so a line mixing Telugu, Hindi and English renders correctly.
- **Edit before you render**: a table lets you correct the lyrics; the timing is kept.
- Exports the **video (.mp4)**, **.srt**, **.ass** and an editable **.json**.
- Web app (Gradio) **and** command line.

## Quick start

You need **Python 3.9+** and **FFmpeg** (with libass/HarfBuzz, which standard builds include; Telugu needs complex-text shaping).

```bash
# 1. FFmpeg
#    Windows:  winget install Gyan.FFmpeg        macOS: brew install ffmpeg
#    Ubuntu:   sudo apt install ffmpeg

# 2. Python packages
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 3. Run the web app  ->  http://127.0.0.1:7860
python app.py
```

On first run the app downloads the free fonts (~a few MB) and, when you first transcribe, the Whisper model (from ~250 MB for `small` up to ~3 GB for `large-v3`). After that it works offline.

### No install: Google Colab

Open `colab.ipynb` in [Google Colab](https://colab.research.google.com) (File → Upload notebook), choose a **T4 GPU** runtime, and run the cells top to bottom. This is also the easy fix if Windows blocks the speech library with *"An Application Control policy has blocked this file"* (Smart App Control).

## Using the web app

1. **Upload** your video, choose the **language** and whether it is **speech** or a **song / music video**, then click **Transcribe**.
2. **Fix the words** in the table. Edit any text; per-word timing is preserved. You can also add or delete rows.
3. Pick a **style preset**, optionally change the animation, fonts, colours, size or position, click **Preview (6 s)**, and when happy **Render full video**.

## Command line

```bash
# everything in one go
python -m captioner run video.mp4 --lang te --song --preset karaoke --model medium

# or in two steps, so you can fix the lyrics in a text editor first
python -m captioner transcribe video.mp4 --lang hi            # writes video.captions.json
python -m captioner render video.mp4 video.captions.json --preset tiktok --highlight "#00E5FF"

python -m captioner presets      # list styles
python -m captioner fonts        # download fonts   (--list shows what is installed)
```

Useful options: `--animation {none,fade,pop,slide_up,zoom,blur_in,slide_left,slide_right,drop,flip,wobble}`, `--word-spacing 1.5` (widen the gap between words), `--latin-font`, `--telugu-font`, `--hindi-font`, `--color`, `--highlight`, `--outline`, `--size 1.2`, `--position {bottom,middle,top}`, `--uppercase`, `--max-words 4`, `--preview`.

## Style presets

| Key | Look |
|---|---|
| `classic` | White text, dark outline, soft fade |
| `karaoke` | Whole line shown; each word fills with colour as it is sung |
| `tiktok` | Big centred text; the active word pops in a bright colour |
| `reveal` | Words fade and pop in one by one |
| `pop` | Each line bounces in |
| `slideup` | Script font; lines glide up into place |
| `neon` | Glowing neon colour sweep |
| `boxed` | Text on a semi-transparent box |
| `comic` | Chunky comic lettering that wobbles in |
| `marker` | Hand-drawn marker karaoke, blurs into focus |
| `elegant` | Graceful script that zooms into place |
| `impact` | Heavy block letters, spoken word flashes, cards flip in |
| `dream` | Soft rounded words sliding in one by one |

Add your own in `captioner/presets.py`: a preset is a few lines (mode, entry animation, fonts, colours, sizes).

## Getting the most accurate Telugu / Hindi

- Use a bigger model: `medium` or `large-v3` (or `large-v3-turbo` for speed) are far better than `small` for Telugu. A 1-minute clip is fine even on a CPU.
- For **songs**, choose *Song / music video*. If the music is loud, tick *Remove background music first* (installs Demucs, see `requirements-optional.txt`); it isolates the vocals before transcription.
- Set the correct language instead of auto-detect, especially for mixed-language lyrics.
- Whisper is not perfect on singing. Always skim the table and fix words before rendering; that is exactly what step 2 is for.

## Fonts

`python -m captioner fonts` downloads these (all SIL OFL) into `./fonts`:

- **Telugu:** Mandali, Ramabhadra, Gurajada, Suravaram, NTR, Dhurjati, Peddana, Ramaraja, Lakki Reddy, Ravi Prakash, Timmana, Tenali Ramakrishna, Sree Krushnadevaraya, Mallanna, Gidugu, Suranna, Sirivennela, Hind Guntur
- **Hindi (Devanagari):** Hind, Mukta, Poppins, Yatra One, Rozha One, Kalam, Tillana, Amita, Sahitya, Khand, Rajdhani, Palanquin, Karma
- **English:** Poppins, Anton, Bebas Neue, Lobster, Pacifico, Bangers, Permanent Marker, Righteous, Lilita One, Bungee, Great Vibes, Satisfy, Press Start 2P

Words running together? Some fonts have a very narrow space. The app widens it automatically; use the **Word spacing** slider (or `--word-spacing`) to fine-tune.

If a download fails (offline / blocked), copy the `.ttf` files into `fonts/` yourself. To add a font, add one line to `captioner/fonts.py` (family name must match the name inside the font file).

## Deploy for free on Hugging Face Spaces

1. Create a new Space (SDK: **Gradio**, hardware: free CPU).
2. Upload this repository's files. `packages.txt` installs FFmpeg for you.
3. Put this block at the very top of the Space's `README.md`:

   ```yaml
   ---
   title: Video Captioner
   sdk: gradio
   app_file: app.py
   ---
   ```

The free CPU tier handles 1-minute clips with the `small` model comfortably; use `base` if it feels slow.

## Project layout

```
app.py                  Gradio web app
captioner/
  transcribe.py         faster-whisper wrapper (word timestamps)
  models.py             Word / Line, chunking, edit-preserving-timing, SRT/JSON
  presets.py            style presets + user overrides
  ass.py                animated ASS subtitle generator (the core)
  fonts.py              font registry, download, per-script fallback
  render.py             ffprobe / ffmpeg: probe, extract audio, burn captions
  vocals.py             optional Demucs vocal separation
  cli.py                command line
tests/                  unit tests + real ffmpeg render tests
```

Run the tests (no model download needed): `python -m unittest discover -s tests -t .`

## Limitations

- Transcription accuracy depends on Whisper. Singing over loud music, fast rap, heavy accents and code-mixed lyrics can need manual correction.
- Videos are limited to 60 s by default (`CAPTIONER_MAX_SECONDS` to change it).
- Captions are burned into the video. Use the exported `.srt` / `.ass` if you want soft subtitles.

## License

Code: [MIT](LICENSE). Whisper models: MIT. Bundled-by-download fonts: SIL Open Font License 1.1 (see each font's page on Google Fonts).
