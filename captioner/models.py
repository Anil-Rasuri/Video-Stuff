"""Data model for timed words / caption lines, plus editing helpers.

A transcript is a list of ``Line`` objects. Each line is a list of ``Word``
objects with start/end times in seconds. Word-level timing is what makes
karaoke-style highlighting and word-by-word animation possible.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, List, Optional, Sequence

from .scripts import grapheme_len

TOL = 0.011  # seconds; rows in the editor table are rounded to 2 decimals


@dataclass
class Word:
    text: str
    start: float
    end: float


@dataclass
class Line:
    words: List[Word]

    @property
    def start(self) -> float:
        return self.words[0].start

    @property
    def end(self) -> float:
        return self.words[-1].end

    @property
    def duration(self) -> float:
        return self.end - self.start

    @property
    def text(self) -> str:
        return " ".join(w.text for w in self.words)

    @classmethod
    def from_text(cls, text: str, start: float, end: float) -> Optional["Line"]:
        """Build a line from plain text, spreading words across [start, end]."""
        texts = text.split()
        if not texts:
            return None
        if end <= start:
            end = start + 0.3 * len(texts)
        return cls(_spread(texts, start, end))

    def with_text(
        self, text: str, start: Optional[float] = None, end: Optional[float] = None
    ) -> Optional["Line"]:
        """Return a copy with new text (and optionally new bounds).

        If the number of words is unchanged the original per-word timing is kept
        (rescaled when the bounds moved). Otherwise words are spread across the
        line in proportion to their length.
        """
        texts = text.split()
        if not texts:
            return None
        s = self.start if start is None else float(start)
        e = self.end if end is None else float(end)
        if e <= s:
            e = s + 0.3 * len(texts)

        if len(texts) == len(self.words):
            if abs(s - self.start) <= TOL and abs(e - self.end) <= TOL:
                return Line([Word(t, w.start, w.end) for t, w in zip(texts, self.words)])
            old_s, old_e = self.start, self.end
            k = (e - s) / (old_e - old_s) if old_e > old_s else 1.0
            return Line(
                [
                    Word(t, s + (w.start - old_s) * k, s + (w.end - old_s) * k)
                    for t, w in zip(texts, self.words)
                ]
            )
        return Line(_spread(texts, s, e))


def _spread(texts: Sequence[str], start: float, end: float) -> List[Word]:
    weights = [max(1, grapheme_len(t)) for t in texts]
    total = float(sum(weights))
    span = end - start
    t = start
    out: List[Word] = []
    for text, wgt in zip(texts, weights):
        nxt = t + span * wgt / total
        out.append(Word(text, t, nxt))
        t = nxt
    out[-1].end = end
    return out


# --------------------------------------------------------------------------
# Clean-up and chunking
# --------------------------------------------------------------------------


def normalize_lines(lines: Sequence[Line]) -> List[Line]:
    """Sort lines, drop empties, make word times monotonic with positive length."""
    cleaned: List[Line] = []
    for ln in sorted((l for l in lines if l.words), key=lambda l: l.start):
        words: List[Word] = []
        t = ln.words[0].start
        for w in ln.words:
            text = w.text.strip()
            if not text:
                continue
            s = max(w.start, t)
            e = max(w.end, s + 0.05)
            words.append(Word(text, s, e))
            t = s
        if words:
            cleaned.append(Line(words))
    return cleaned


def chunk_lines(
    lines: Sequence[Line],
    max_words: int = 5,
    max_seconds: float = 4.0,
    max_gap: float = 1.0,
) -> List[Line]:
    """Split long phrases into short, balanced caption lines.

    Splits first at silent gaps (instrumental breaks, pauses), then into
    evenly sized chunks no longer than ``max_words`` words / ``max_seconds``.
    """
    max_words = max(1, int(max_words))
    out: List[Line] = []
    for line in lines:
        if not line.words:
            continue
        groups: List[List[Word]] = [[line.words[0]]]
        for prev, w in zip(line.words, line.words[1:]):
            if w.start - prev.end > max_gap:
                groups.append([w])
            else:
                groups[-1].append(w)
        for g in groups:
            n = len(g)
            dur = g[-1].end - g[0].start
            parts = math.ceil(n / max_words)
            if max_seconds:
                parts = max(parts, math.ceil(dur / max_seconds))
            parts = max(1, min(parts, n))
            base, extra = divmod(n, parts)
            i = 0
            for p in range(parts):
                size = base + (1 if p < extra else 0)
                out.append(Line(g[i : i + size]))
                i += size
    return out


# --------------------------------------------------------------------------
# Editor table <-> lines
# --------------------------------------------------------------------------


def lines_to_rows(lines: Sequence[Line]) -> List[List[Any]]:
    return [[round(l.start, 2), round(l.end, 2), l.text] for l in lines]


def _num(x: Any) -> Optional[float]:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(v) else v


def rows_to_lines(rows: Sequence[Sequence[Any]], originals: Sequence[Line]) -> List[Line]:
    """Turn (possibly edited) table rows back into lines.

    Word-level timing from the original transcript is preserved wherever
    possible, so editing a typo does not destroy the karaoke sync.
    """
    parsed = []
    for row in rows:
        if row is None or len(row) < 3:
            continue
        s, e, text = _num(row[0]), _num(row[1]), row[2]
        if text is None or (isinstance(text, float) and math.isnan(text)):
            continue
        text = str(text).strip()
        if not text or s is None:
            continue
        if e is None or e <= s:
            e = s + max(0.5, 0.3 * len(text.split()))
        parsed.append((s, e, text))

    out: List[Line] = []
    if len(parsed) == len(originals):
        # Same number of rows: edits in place (text and/or times).
        for (s, e, text), orig in zip(parsed, originals):
            line = orig.with_text(text, s, e)
            if line:
                out.append(line)
    else:
        # Rows were added or removed: match by timing where we can.
        used = set()
        for s, e, text in parsed:
            match = None
            for i, orig in enumerate(originals):
                if i not in used and abs(orig.start - s) <= TOL and abs(orig.end - e) <= TOL:
                    match = i
                    break
            if match is not None:
                used.add(match)
                line = originals[match].with_text(text)
            else:
                line = Line.from_text(text, s, e)
            if line:
                out.append(line)
    return normalize_lines(out)


# --------------------------------------------------------------------------
# Serialisation
# --------------------------------------------------------------------------


def lines_to_dict(lines: Sequence[Line]) -> dict:
    return {
        "version": 1,
        "lines": [
            {
                "words": [
                    {"text": w.text, "start": round(w.start, 3), "end": round(w.end, 3)}
                    for w in l.words
                ]
            }
            for l in lines
        ],
    }


def lines_from_dict(data: dict) -> List[Line]:
    lines = []
    for item in data.get("lines", []):
        words = [Word(str(w["text"]), float(w["start"]), float(w["end"])) for w in item["words"]]
        if words:
            lines.append(Line(words))
    return normalize_lines(lines)


def save_lines(lines: Sequence[Line], path) -> Path:
    path = Path(path)
    path.write_text(
        json.dumps(lines_to_dict(lines), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return path


def load_lines(path) -> List[Line]:
    return lines_from_dict(json.loads(Path(path).read_text(encoding="utf-8")))


def _srt_time(t: float) -> str:
    ms = max(0, int(round(t * 1000)))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return "%02d:%02d:%02d,%03d" % (h, m, s, ms)


def to_srt(lines: Sequence[Line]) -> str:
    blocks = []
    for i, l in enumerate(lines, 1):
        blocks.append("%d\n%s --> %s\n%s\n" % (i, _srt_time(l.start), _srt_time(l.end), l.text))
    return "\n".join(blocks)
