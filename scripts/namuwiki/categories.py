"""Titles, redirects and categories ([[분류:...]]) of Namu Wiki records."""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping

# title prefix -> namespace. The dump's "namespace" field is always 0, so we use the prefix.
NAMESPACE_PREFIXES = ("틀", "분류", "나무위키", "파일", "사용자", "토론", "특수기능", "휴지통")
DOCUMENT = "문서"

CAT_RE = re.compile(r"\[\[\s*분류\s*:\s*([^\]\|\n]+?)\s*(?:\|[^\]]*)?\]\]")
# on a category page, '[[분류:X|Y]]' (with a pipe) is a listing link, not a parent
PARENT_RE = re.compile(r"\[\[\s*분류\s*:\s*([^\]\|\n]+?)\s*\]\]")
# where the listing of sub-categories / member pages starts on a category page
LISTING_RE = re.compile(r"^==\s*(하위 분류|\".*\" 분류에 속하는)", re.M)

REDIRECT = "#redirect"


def namespace_of(title: str) -> str:
    if ":" in title:
        prefix = title.split(":", 1)[0]
        if prefix in NAMESPACE_PREFIXES:
            return prefix
    return DOCUMENT


def redirect_target(text: str) -> str | None:
    """'#redirect 방탄소년단' -> '방탄소년단'. None if the text is not a redirect."""
    head = text.lstrip()
    if head[: len(REDIRECT)].lower() != REDIRECT:
        return None
    return head.split("\n", 1)[0][len(REDIRECT):].strip()


def _clean_names(names: Iterable[str]) -> list[str]:
    out: list[str] = []
    for c in names:
        c = c.strip()
        if c.endswith("#blur"):
            c = c[: -len("#blur")].strip()
        if c and c not in out:
            out.append(c)
    return out


def page_categories(text: str) -> list[str]:
    """Categories written in a document, in order, without duplicates."""
    return _clean_names(CAT_RE.findall(text))


def parent_categories(text: str) -> list[str]:
    """Parent categories of a category page ('분류:X').

    Only links before the listing section count, and piped links are skipped.
    """
    m = LISTING_RE.search(text)
    head = text[: m.start()] if m else text
    return _clean_names(PARENT_RE.findall(head))


def category_name(title: str) -> str:
    """'분류:나연' -> '나연'"""
    return title.split(":", 1)[1].strip()


def effective_categories(
    title: str, own: Iterable[str], parents: Mapping[str, Iterable[str]]
) -> set[str]:
    """Own categories plus the parents of the document's own-name category (one level).

    Popular stars often only have [[분류:<title>]] in the document; the real categories
    (한국 여가수, 1995년 출생, TWICE/멤버 ...) sit on the page 분류:<title>.
    """
    cats = set(own)
    if title in cats and title in parents:
        cats |= set(parents[title])
    return cats
