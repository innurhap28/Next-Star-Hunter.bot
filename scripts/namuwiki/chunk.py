"""Split cleaned text into paragraph chunks of about 500-1000 characters.

Section boundaries are kept: a chunk never mixes two sections, except that short
neighbouring pieces are merged and the later section title is written inline ('[여담]').
"""

from __future__ import annotations

import re

from .clean import HEADING_RE

MIN_CHARS = 500
MAX_CHARS = 1000
# navigation-only sections, nothing to search in them
SKIP_SECTIONS = re.compile(r"^(둘러보기|관련 문서|같이 보기|외부 링크|각주|틀)$")
SENT_SPLIT = re.compile(r"(?<=[.!?다요])\s+")


def sections(clean_text: str) -> list[tuple[str, str]]:
    """[(section path, body)] using the '== title ==' lines. Text before any heading is '개요'."""
    cur: list[str] = []
    path: list[str] = []
    out = []
    for line in clean_text.split("\n"):
        m = HEADING_RE.match(line.strip())
        if m:
            if "".join(cur).strip():
                out.append((" > ".join(path) or "개요", "\n".join(cur).strip()))
            level = len(m.group(1))
            path = path[: max(0, level - 2)] + [m.group(2)]
            cur = []
        else:
            cur.append(line)
    if "".join(cur).strip():
        out.append((" > ".join(path) or "개요", "\n".join(cur).strip()))
    return out


def _pieces(body: str, max_chars: int) -> list[str]:
    """Paragraphs no longer than max_chars (long ones split at sentence ends, then hard)."""
    out = []
    for p in re.split(r"\n\s*\n", body):
        p = p.strip()
        if not p:
            continue
        if len(p) <= max_chars:
            out.append(p)
            continue
        buf = ""
        for s in SENT_SPLIT.split(p):
            while len(s) > max_chars:
                if buf:
                    out.append(buf)
                    buf = ""
                out.append(s[:max_chars])
                s = s[max_chars:]
            if buf and len(buf) + len(s) + 1 > max_chars:
                out.append(buf)
                buf = s
            else:
                buf = f"{buf} {s}".strip()
        if buf:
            out.append(buf)
    return out


def chunk(
    clean_text: str,
    min_chars: int = MIN_CHARS,
    max_chars: int = MAX_CHARS,
    skip_sections: re.Pattern | None = SKIP_SECTIONS,
) -> list[tuple[str, str]]:
    """[(section, content)] with every content at most max_chars long."""
    chunks: list[tuple[str, str]] = []
    for sec, body in sections(clean_text):
        last = sec.split(" > ")[-1]
        if skip_sections is not None and skip_sections.search(last):
            continue
        buf = ""
        for p in _pieces(body, max_chars):
            if buf and len(buf) + len(p) + 2 > max_chars:
                chunks.append((sec, buf))
                buf = p
            else:
                buf = f"{buf}\n\n{p}" if buf else p
            if len(buf) >= min_chars:
                chunks.append((sec, buf))
                buf = ""
        if buf:
            if chunks and chunks[-1][0] == sec and len(chunks[-1][1]) + len(buf) + 2 <= max_chars:
                chunks[-1] = (sec, chunks[-1][1] + "\n\n" + buf)
            else:
                chunks.append((sec, buf))

    # merge short neighbours (short sections) while they fit
    merged: list[tuple[str, str]] = []
    for sec, body in chunks:
        if merged:
            psec, pbody = merged[-1]
            short = len(pbody) < min_chars or len(body) < min_chars // 2
            head = "" if sec == psec else f"[{sec}]\n"
            if short and len(pbody) + 2 + len(head) + len(body) <= max_chars:
                name = psec if sec == psec else f"{psec} | {sec}"
                merged[-1] = (name, f"{pbody}\n\n{head}{body}")
                continue
        merged.append((sec, body))
    return merged
