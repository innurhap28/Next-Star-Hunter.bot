"""Extract Korean star documents from a Namu Wiki dump into JSONL files.

    python -m scripts.namuwiki.extract --dump dump.json --out data/namu

The dump is read twice:
  1. titles, redirects and categories of every record, plus the parent categories of
     every '분류:' page. Selection rules run on this.
  2. the text of the selected records is written out.

Output files (one JSON object per line, UTF-8):
  persons.jsonl   {"title", "kind": "person", "signals", "categories", "text"}
  groups.jsonl    {"title", "kind": "group", "categories", "text"}
  subdocs.jsonl   {"title", "kind": "subdoc", "parent", "parent_kind", "categories", "text"}
  aliases.jsonl   {"title", "kind": "alias", "target", "categories", "text"}
  stats.json      counters
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import Counter
from collections.abc import Iterable
from typing import TextIO

from . import categories as C
from .reader import DEFAULT_CHUNK_SIZE, DEFAULT_MAX_RECORD_CHARS, iter_records
from .rules import Selection, select

OUTPUT_FILES = ("persons", "groups", "subdocs", "aliases")


class Pass1:
    """What pass 1 keeps in memory (no document text)."""

    def __init__(self) -> None:
        self.own: dict[str, tuple] = {}  # root document title -> own categories
        self.parents: dict[str, list[str]] = {}  # category name -> parent categories
        self.redirects: dict[str, str] = {}  # document redirect title -> target
        self.subdoc_titles: set[str] = set()  # non-redirect documents with '/'
        self.stats: Counter = Counter()
        self._names: dict[str, str] = {}

    def _intern(self, names: Iterable[str]) -> tuple:
        # the same category names repeat a lot; share the strings
        return tuple(self._names.setdefault(n, n) for n in names)

    def add(self, rec: dict) -> None:
        title = rec.get("title") or ""
        text = rec.get("text") or ""
        ns = C.namespace_of(title)
        self.stats["ns:" + ns] += 1
        target = C.redirect_target(text)
        if target is not None:
            self.stats["redirects"] += 1
            if ns == C.DOCUMENT:
                self.redirects[title] = target
            return
        if ns == "분류":
            self.parents[C.category_name(title)] = list(
                self._intern(C.parent_categories(text))
            )
        elif ns == C.DOCUMENT:
            if "/" in title:
                self.subdoc_titles.add(title)
            else:
                self.own[title] = self._intern(C.page_categories(text))

    def effective(self) -> dict[str, set[str]]:
        return {
            t: C.effective_categories(t, own, self.parents) for t, own in self.own.items()
        }


def alias_key(target: str) -> str:
    """'방탄소년단#s-2' -> '방탄소년단'"""
    return target.split("#", 1)[0].strip()


def plan_subdocs(subdoc_titles: Iterable[str], sel: Selection) -> dict[str, str]:
    """subdoc title -> parent title, for sub-documents of selected persons/groups."""
    out = {}
    for t in subdoc_titles:
        parent = t.split("/", 1)[0]
        if sel.kind_of(parent):
            out[t] = parent
    return out


def plan_aliases(redirects: dict[str, str], targets: set[str]) -> dict[str, str]:
    return {a: t for a, t in redirects.items() if alias_key(t) in targets}


def _write(f: TextIO, obj: dict) -> None:
    f.write(json.dumps(obj, ensure_ascii=False) + "\n")


def run(
    dump: str,
    out_dir: str,
    known_groups: Iterable[str] = (),
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    max_record_chars: int = DEFAULT_MAX_RECORD_CHARS,
    log: TextIO | None = None,
) -> dict:
    os.makedirs(out_dir, exist_ok=True)
    t0 = time.time()

    def note(msg: str) -> None:
        if log is not None:
            log.write(f"[{time.time() - t0:7.1f}s] {msg}\n")
            log.flush()

    # pass 1
    p1 = Pass1()
    read1: Counter = Counter()
    for i, rec in enumerate(iter_records(dump, chunk_size, max_record_chars, read1), 1):
        p1.add(rec)
        if i % 200000 == 0:
            note(f"pass1 {i} records")
    note(f"pass1 done: {read1['records']} records")

    sel = select(p1.effective(), known_groups)
    subdocs = plan_subdocs(p1.subdoc_titles, sel)
    targets = set(sel.persons) | sel.groups | set(subdocs)
    aliases = plan_aliases(p1.redirects, targets)
    note(f"selected persons={len(sel.persons)} groups={len(sel.groups)} "
         f"subdocs={len(subdocs)} aliases={len(aliases)}")

    # pass 2
    files = {name: open(os.path.join(out_dir, name + ".jsonl"), "w", encoding="utf-8")
             for name in OUTPUT_FILES}
    written: Counter = Counter()
    seen: set[str] = set()
    read2: Counter = Counter()
    try:
        for rec in iter_records(dump, chunk_size, max_record_chars, read2):
            title = rec.get("title") or ""
            if title in seen:
                continue
            text = rec.get("text") or ""
            is_redirect = C.redirect_target(text) is not None
            if is_redirect:
                if title in aliases:
                    _write(files["aliases"], {"title": title, "kind": "alias",
                                              "target": aliases[title], "categories": [],
                                              "text": text})
                    written["aliases"] += 1
                    seen.add(title)
                continue
            if C.namespace_of(title) != C.DOCUMENT:
                continue
            kind = sel.kind_of(title)
            if kind is not None:
                eff = C.effective_categories(title, C.page_categories(text), p1.parents)
                obj = {"title": title, "kind": kind}
                if kind == "person":
                    obj["signals"] = sel.persons[title]
                obj["categories"] = sorted(eff)
                obj["text"] = text
                _write(files[kind + "s"], obj)
                written[kind + "s"] += 1
                seen.add(title)
            elif title in subdocs:
                parent = subdocs[title]
                _write(files["subdocs"], {"title": title, "kind": "subdoc", "parent": parent,
                                          "parent_kind": sel.kind_of(parent),
                                          "categories": C.page_categories(text),
                                          "text": text})
                written["subdocs"] += 1
                seen.add(title)
    finally:
        for f in files.values():
            f.close()
    note("pass2 done")

    stats = {
        "dump_bytes": os.path.getsize(dump),
        "elapsed_sec": round(time.time() - t0, 1),
        "read": dict(read1),
        "pass1": dict(sorted(p1.stats.items())),
        "category_pages": len(p1.parents),
        "rule": dict(sorted(sel.stats.items())),
        "written": {name: written[name] for name in OUTPUT_FILES},
        "subdocs_person": sum(1 for p in subdocs.values() if p in sel.persons),
        "subdocs_group": sum(1 for p in subdocs.values() if p in sel.groups),
        "aliases_to_person_or_group": sum(
            1 for t in aliases.values() if sel.kind_of(alias_key(t))
        ),
    }
    with open(os.path.join(out_dir, "stats.json"), "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=1)
    return stats


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="python -m scripts.namuwiki.extract",
        description="Extract Korean star documents from a Namu Wiki dump into JSONL files.",
    )
    ap.add_argument("--dump", required=True, help="dump JSON file (one JSON array)")
    ap.add_argument("--out", required=True, help="output directory")
    ap.add_argument("--known-group", action="append", default=[],
                    help="extra group title used for the member rule (repeatable)")
    ap.add_argument("--chunk-mb", type=int, default=DEFAULT_CHUNK_SIZE >> 20,
                    help="read size in MiB (default: %(default)s)")
    ap.add_argument("--max-record-mb", type=int, default=DEFAULT_MAX_RECORD_CHARS >> 20,
                    help="skip records longer than N * 2^20 characters (default: %(default)s)")
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args(argv)
    stats = run(a.dump, a.out, a.known_group, a.chunk_mb << 20, a.max_record_mb << 20,
                log=None if a.quiet else sys.stderr)
    print(json.dumps({"written": stats["written"], "read": stats["read"],
                      "elapsed_sec": stats["elapsed_sec"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
