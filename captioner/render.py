"""ffmpeg plumbing: probe, extract audio, burn animated captions into the video."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Sequence

from . import fonts as fontlib
from .ass import build_ass
from .models import Line, save_lines, to_srt
from .presets import StyleOptions, resolve_style

MAX_SECONDS = float(os.environ.get("CAPTIONER_MAX_SECONDS", "120"))


class RenderError(RuntimeError):
    pass


@dataclass
class VideoInfo:
    width: int
    height: int
    duration: float
    has_audio: bool


@dataclass
class RenderResult:
    video: Path
    ass: Path
    srt: Path
    json: Path
    warnings: List[str] = field(default_factory=list)


def _require(tool: str) -> str:
    exe = shutil.which(tool)
    if not exe:
        raise RenderError(
            "%s was not found. Install FFmpeg (https://ffmpeg.org/download.html) and make sure it is on your PATH."
            % tool
        )
    return exe


def _run(cmd: Sequence[str], cwd: Optional[Path] = None) -> str:
    proc = subprocess.run(list(cmd), cwd=str(cwd) if cwd else None, capture_output=True, text=True)
    if proc.returncode != 0:
        tail = "\n".join((proc.stderr or "").strip().splitlines()[-12:])
        raise RenderError("%s failed:\n%s" % (Path(cmd[0]).name, tail))
    return proc.stdout


def probe(path) -> VideoInfo:
    """Read size (after rotation metadata), duration and audio presence."""
    out = _run(
        [
            _require("ffprobe"),
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            str(path),
        ]
    )
    data = json.loads(out)
    video = next((s for s in data.get("streams", []) if s.get("codec_type") == "video"), None)
    if video is None:
        raise RenderError("No video stream found in %s" % path)
    width, height = int(video["width"]), int(video["height"])

    rotation = 0
    for sd in video.get("side_data_list", []) or []:
        if "rotation" in sd:
            rotation = int(round(float(sd["rotation"])))
    tag_rot = (video.get("tags") or {}).get("rotate")
    if tag_rot:
        rotation = int(float(tag_rot))
    if abs(rotation) % 180 == 90:
        width, height = height, width

    duration = 0.0
    for src in (data.get("format", {}), video):
        try:
            duration = float(src.get("duration"))
            break
        except (TypeError, ValueError):
            continue
    has_audio = any(s.get("codec_type") == "audio" for s in data.get("streams", []))
    return VideoInfo(width, height, duration, has_audio)


def extract_audio(video, wav_path) -> Path:
    """16 kHz mono WAV, the format speech models like best."""
    wav_path = Path(wav_path)
    _run(
        [
            _require("ffmpeg"),
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(video),
            "-vn",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-c:a",
            "pcm_s16le",
            str(wav_path),
        ]
    )
    return wav_path


def check_duration(info: VideoInfo, max_seconds: Optional[float] = None) -> None:
    limit = MAX_SECONDS if max_seconds is None else max_seconds
    if limit and info.duration > limit + 0.75:
        raise ValueError(
            "Video is %.1f s long; this tool is limited to %.0f s. "
            "Trim it first (or raise CAPTIONER_MAX_SECONDS)." % (info.duration, limit)
        )


def render_captions(
    video,
    lines: Sequence[Line],
    options: Optional[StyleOptions] = None,
    out_dir=None,
    *,
    preview: bool = False,
    preview_seconds: float = 6.0,
    max_seconds: Optional[float] = None,
) -> RenderResult:
    """Burn animated captions into ``video`` and write .mp4/.ass/.srt/.json files."""
    options = options or StyleOptions()
    video = Path(video)
    ffmpeg = _require("ffmpeg")
    info = probe(video)
    check_duration(info, max_seconds)
    if not lines:
        raise ValueError("There are no caption lines to render.")

    out_dir = Path(out_dir) if out_dir else Path(tempfile.mkdtemp(prefix="captioner_"))
    out_dir.mkdir(parents=True, exist_ok=True)

    style = resolve_style(options)
    style, warnings = fontlib.resolve_style_fonts(style)

    work = out_dir / "_work"
    work.mkdir(parents=True, exist_ok=True)
    fontlib.stage_fonts([style.latin_font, style.telugu_font, style.devanagari_font], work / "fonts")

    ass_text = build_ass(lines, info.width, info.height, style)
    (work / "captions.ass").write_text(ass_text, encoding="utf-8")

    suffix = "_preview" if preview else ""
    out_video = out_dir / ("%s_captioned%s.mp4" % (video.stem, suffix))

    cmd = [ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", str(video.resolve())]
    if preview:
        start = max(0.0, min(l.start for l in lines) - 0.5)
        cmd += ["-ss", "%.3f" % start, "-t", "%.3f" % preview_seconds]
    cmd += [
        "-map",
        "0:v:0",
        "-map",
        "0:a:0?",
        "-vf",
        "ass=captions.ass:fontsdir=fonts,scale=trunc(iw/2)*2:trunc(ih/2)*2",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "20",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-movflags",
        "+faststart",
        str(out_video),
    ]
    _run(cmd, cwd=work)

    ass_path = out_dir / (video.stem + ".ass")
    srt_path = out_dir / (video.stem + ".srt")
    json_path = out_dir / (video.stem + ".captions.json")
    ass_path.write_text(ass_text, encoding="utf-8")
    srt_path.write_text(to_srt(lines), encoding="utf-8")
    save_lines(lines, json_path)
    shutil.rmtree(work, ignore_errors=True)

    return RenderResult(out_video, ass_path, srt_path, json_path, warnings)
