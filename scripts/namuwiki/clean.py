"""Namumark -> plain text.

Rough on purpose: we only need readable text for search and answers, not a renderer.
Headings are kept as '== title ==' lines so chunk.py can split on them.
"""

from __future__ import annotations

import re

CAT_RE = re.compile(r"\[\[\s*분류\s*:[^\]]*\]\]")
# one level of [ ] is allowed inside links: '[[IDOL [아이돌 : The Coup]]]'
_IN = r"(?:[^\[\]|]|\[[^\[\]]*\])*"
FILE_RE = re.compile(r"\[\[\s*파일\s*:(?:[^\[\]]|\[[^\[\]]*\])*\]\]")
# external links: the label is usually '기사', an icon or a title; drop the whole link
EXT_LINK_RE = re.compile(r"\[\[\s*https?://[^\]|]*(?:\|(?:[^\[\]]|\[[^\[\]]*\])*)?\]\]")
MACRO_RE = re.compile(
    r"\[(include|youtube|nicovideo|kakaotv|vimeo|navertv|ruby|dday|pagecount|anchor)"
    r"\s*\([^\]]*\)\]",
    re.I,
)
AGE_RE = re.compile(r"\(?\s*\[age\([^)]*\)\]\s*세\s*\)?|\[age\([^)]*\)\]", re.I)
SIMPLE_MACRO_RE = re.compile(
    r"\[(clearfix|tableofcontents|목차|각주|footnote|date|datetime)\]", re.I
)
BR_RE = re.compile(r"\[br\]|<br\s*/?>", re.I)
BRACE_INNER_RE = re.compile(
    r"\{\{\{(?:[+-]\d\s|#[0-9A-Za-z,#]+\s|#!(?:wiki|folding)[^\n]*\n)?([^{}]*?)\}\}\}", re.S
)
HTML_BLOCK_RE = re.compile(r"\{\{\{#!(?:html|syntax|latex)[^{}]*?\}\}\}", re.S)
LINK_PIPE_RE = re.compile(r"\[\[(" + _IN + r")\|((?:[^\[\]]|\[[^\[\]]*\])*)\]\]")
LINK_RE = re.compile(r"\[\[(" + _IN + r")\]\]")
WIKI_ATTR_RE = re.compile(r"#!(?:wiki|folding)(?:\s+style=\"[^\"]*\")?")
# table pieces left in the middle of a line (tables inside one-line {{{#!wiki}}} boxes)
INLINE_CELL_RE = re.compile(r"\s*\|\|(?:\s*<[^<>]{0,120}>)*\s*")
HEADING_RE = re.compile(r"^(={1,6})#?\s*(.*?)\s*#?\1\s*$", re.M)
CELL_ATTR_RE = re.compile(r"^(\s*<[^<>]{0,120}>)+")
FMT_RE = [
    (re.compile(r"'''(.*?)'''"), r"\1"),
    (re.compile(r"''(.*?)''"), r"\1"),
    (re.compile(r"__(.*?)__"), r"\1"),
    (re.compile(r"~~(.*?)~~"), ""),
    (re.compile(r"--(.*?)--"), ""),
    (re.compile(r"\^\^(.*?)\^\^"), r"\1"),
    (re.compile(r",,(.*?),,"), r"\1"),
]
INLINE_HTML_RE = re.compile(r"</?(span|font|div|nowiki|pre|sup|sub)[^>]*>", re.I)
# lines that only point somewhere else or talk about the wiki itself
BOILER_RE = re.compile(
    r"(편집 보호된 문서입니다|ACL 탭|문서를 참고하십시오|여기로 연결됩니다|이 문서는 .*(분류|토론)|"
    r"이 저작물은 CC BY-NC-SA)"
)
# values frozen at crawl time: '(데뷔일로부터 +3,512일, 10주년)', '1992년 3월 18일 (34세)'
SINCE_RE = re.compile(r"\s*\(\s*[^()\n]{0,12}로부터\s*\+?[\d,]+\s*일[^()\n]{0,12}\)")
AGE_NOW_RE = re.compile(r"(\d\s*일)\s*\(\s*(?:만\s*)?\d{1,3}\s*세\s*\)")

BR = "\x00"  # placeholder for [br]: ' / ' inside table cells, newline elsewhere


def strip_balanced(text: str, opener: str) -> str:
    """Remove every `opener ... ]` keeping nested [ ] balanced (footnotes: '[*')."""
    out, i, n = [], 0, len(text)
    while True:
        j = text.find(opener, i)
        if j < 0:
            out.append(text[i:])
            break
        out.append(text[i:j])
        depth, k = 0, j
        while k < n:
            c = text[k]
            if c == "[":
                depth += 1
            elif c == "]":
                depth -= 1
                if depth == 0:
                    break
            k += 1
        i = k + 1
    return "".join(out)


def link_target(target: str) -> str:
    target = target.strip()
    if target.startswith(":"):
        target = target[1:]
    return target.split("#", 1)[0].strip()


def _plain_link(m: re.Match) -> str:
    target = m.group(1)
    return "" if target.strip().startswith("http") else link_target(target)


def _piped_link(m: re.Match) -> str:
    # external link labels are usually '기사', icons or bare urls; drop them
    return "" if m.group(1).strip().startswith("http") else m.group(2)


def inline(text: str) -> str:
    """Inline markup -> plain text (no table or heading handling)."""
    text = HTML_BLOCK_RE.sub("", text)
    for _ in range(6):  # unwrap {{{ }}} from the innermost one
        new = BRACE_INNER_RE.sub(r"\1", text)
        if new == text:
            break
        text = new
    text = re.sub(r"\{\{\{#!(wiki|folding)[^\n]*\n?", "", text)
    text = text.replace("{{{", "").replace("}}}", "")
    text = WIKI_ATTR_RE.sub("", text)
    text = EXT_LINK_RE.sub("", text)
    for _ in range(4):  # links inside link labels
        new = LINK_PIPE_RE.sub(_piped_link, text)
        new = LINK_RE.sub(_plain_link, new)
        if new == text:
            break
        text = new
    # links with unbalanced brackets in the source: drop the url, keep the words
    text = re.sub(r"\[\[\s*https?://[^\s|\]]*\]?\|?", "", text)
    text = text.replace("[[", "").replace("]]", "")
    for rx, rep in FMT_RE:
        text = rx.sub(rep, text)
    return INLINE_HTML_RE.sub(" ", text)


def pre(text: str) -> str:
    """Whole-text removals; links and {{{ }}} may span lines so this runs before splitting."""
    text = CAT_RE.sub("", text)
    text = FILE_RE.sub("", text)
    text = MACRO_RE.sub("", text)
    text = AGE_RE.sub("", text)
    text = BR_RE.sub(BR, text)
    text = SIMPLE_MACRO_RE.sub("", text)
    text = strip_balanced(text, "[*")
    text = inline(text)
    text = SINCE_RE.sub("", text)
    return AGE_NOW_RE.sub(r"\1", text)


def join_table_rows(lines: list[str]) -> list[str]:
    """A table row may span several lines ('|| a\\nb || c ||'); join them with BR."""
    out: list[str] = []
    buf = None
    for line in lines:
        s = line.strip()
        if buf is not None:
            buf += BR + s
            if s.endswith("||"):
                out.append(buf)
                buf = None
            continue
        if s.startswith("||") and not (s.endswith("||") and len(s) > 2):
            buf = s
            continue
        out.append(line)
    if buf is not None:
        out.append(buf)
    return out


def table_cells(line: str) -> list[str]:
    cells = [CELL_ATTR_RE.sub("", c).strip() for c in line.strip().strip("|").split("||")]
    cells = [re.sub(r"\s+", " ", c.replace(BR, " / ")).strip(" /") for c in cells]
    return [c for c in cells if c]


def lead_and_body(text: str) -> tuple[str, str]:
    """Split at the first heading. The lead holds navigation boxes and the infobox."""
    m = HEADING_RE.search(text)
    return (text[: m.start()], text[m.start():]) if m else (text, "")


def clean(text: str, drop_lead: bool = True) -> str:
    """Namumark -> plain text.

    drop_lead: the part before the first heading is navigation boxes + infobox. The
    infobox goes to the profile (profile.py), so it is dropped from the prose by default.
    Documents without any heading keep everything.
    """
    text = pre(text)
    if drop_lead:
        _, body = lead_and_body(text)
        if body:
            text = body
    out = []
    for line in join_table_rows(text.split("\n")):
        s = line.strip()
        if not s:
            out.append("")
            continue
        m = HEADING_RE.match(s)
        if m:
            title = m.group(2).replace(BR, " ").strip()
            out.append(f"{m.group(1)} {title} {m.group(1)}")
            continue
        if s.startswith("||"):
            cells = table_cells(s)
            if not cells:
                continue
            if len(cells) == 2 and len(cells[0]) <= 12:
                out.append(f"{cells[0]}: {cells[1]}")
            else:
                out.append(" | ".join(cells))
            continue
        if "||" in s:
            s = re.sub(r"(?:\s*\|)+\s*", " | ", INLINE_CELL_RE.sub(" | ", s)).strip(" |")
        s = re.sub(r"^\*\s*", "- ", s)
        s = s.lstrip(">").strip()
        s = s.replace(BR, "\n")
        if not s.strip() or BOILER_RE.search(s):
            continue
        out.append(re.sub(r"[ \t]+", " ", s))
    text = "\n".join(out).replace(BR, "\n")
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
