"""Clean, chunk and load the extract output into star_profiles / star_chunks.

    python -m scripts.namuwiki.load --input data/namu --database-url "$DATABASE_URL"

Input is the folder written by scripts.namuwiki.extract (persons/groups/subdocs/aliases
.jsonl). Every run replaces both tables inside one transaction, so running it again
gives the same rows and a failed run leaves the old rows in place.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from collections import defaultdict
from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path
from typing import TextIO
from urllib.parse import quote

from sqlalchemy import text

from .chunk import chunk
from .clean import clean
from .extract import alias_key
from .profile import build_profile, group_gender, profile_text

BACKEND = Path(__file__).resolve().parents[2] / "backend"
if str(BACKEND) not in sys.path:  # 'app' lives in backend/ (pytest adds it via pythonpath)
    sys.path.insert(0, str(BACKEND))

from app.database import Base, build_engine  # noqa: E402
from app.models import StarChunk, StarProfile  # noqa: E402

LICENSE = "CC BY-NC-SA 2.0 KR"
LICENSE_URL = "https://creativecommons.org/licenses/by-nc-sa/2.0/kr/"
# sub-documents that are mostly lists, fancams, chants or incidents (see docs/DATA.md)
SKIP_SUBDOC_RE = re.compile(
    r"직캠|응원법|노래방|굿즈|차트|V LIVE|Weverse|유튜브|콘텐츠|커버곡|논란|사건|사고|광고|화보|"
    r"공연 및 행사|음반 목록|디스코그래피|음반$|팬덤|멤버 간 케미"
)
SECTION_MAX = 200
TABLES = [StarProfile.__table__, StarChunk.__table__]
# (name, PostgreSQL statement). Built after the rows are in, dropped before reloading.
TRGM_INDEXES = [
    ("ix_star_profiles_title_trgm",
     "CREATE INDEX ix_star_profiles_title_trgm ON star_profiles USING gin (title gin_trgm_ops)"),
    ("ix_star_profiles_aliases_trgm",
     "CREATE INDEX ix_star_profiles_aliases_trgm ON star_profiles "
     "USING gin (aliases gin_trgm_ops)"),
    ("ix_star_chunks_content_trgm",
     "CREATE INDEX ix_star_chunks_content_trgm ON star_chunks USING gin (content gin_trgm_ops)"),
]
FTS_INDEXES = [
    ("ix_star_profiles_names_fts",
     "CREATE INDEX ix_star_profiles_names_fts ON star_profiles "
     "USING gin (to_tsvector('simple', title || ' ' || aliases))"),
    ("ix_star_chunks_content_fts",
     "CREATE INDEX ix_star_chunks_content_fts ON star_chunks "
     "USING gin (to_tsvector('simple', content))"),
]


def source_url(title: str) -> str:
    """'아이유/여담' -> 'https://namu.wiki/w/%EC%95%84%EC%9D%B4%EC%9C%A0/%EC%97%AC%EB%8B%B4'"""
    return "https://namu.wiki/w/" + quote(title, safe="/")


def read_jsonl(path: Path) -> Iterator[dict]:
    if not path.exists():
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                yield json.loads(line)


def read_redirects(input_dir: Path) -> dict[str, list[str]]:
    """target title -> redirect titles pointing at it."""
    out: dict[str, list[str]] = defaultdict(list)
    for rec in read_jsonl(input_dir / "aliases.jsonl"):
        out[alias_key(rec.get("target") or "")].append(rec["title"])
    return out


def doc_chunks(raw_text: str, section_prefix: str = "") -> list[tuple[str, str]]:
    out = []
    for sec, content in chunk(clean(raw_text)):
        if section_prefix:
            sec = f"{section_prefix} > {sec}" if sec != "개요" else section_prefix
        out.append((sec[:SECTION_MAX], content))
    return out


class Writer:
    """Collects rows and inserts them in batches."""

    def __init__(self, conn, batch: int) -> None:
        self.conn = conn
        self.batch = batch
        self.profiles: list[dict] = []
        self.chunks: list[dict] = []
        self.counts = {"profiles": 0, "chunks": 0}

    def add_profile(self, row: dict) -> None:
        self.profiles.append(row)
        if len(self.profiles) >= self.batch:
            self.flush()

    def add_chunk(self, row: dict) -> None:
        self.chunks.append(row)
        if len(self.chunks) >= self.batch:
            self.flush()

    def flush(self) -> None:
        # profiles first: chunk rows point at them
        if self.profiles:
            self.conn.execute(StarProfile.__table__.insert(), self.profiles)
            self.counts["profiles"] += len(self.profiles)
            self.profiles = []
        if self.chunks:
            self.conn.execute(StarChunk.__table__.insert(), self.chunks)
            self.counts["chunks"] += len(self.chunks)
            self.chunks = []


def _drop_search_indexes(conn) -> None:
    for name, _ in TRGM_INDEXES + FTS_INDEXES:
        conn.execute(text(f"DROP INDEX IF EXISTS {name}"))


def _create_search_indexes(conn) -> str:
    """pg_trgm GIN indexes if the extension can be used, else 'simple' full-text indexes."""
    try:
        with conn.begin_nested():
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
    except Exception:
        pass
    has_trgm = conn.execute(
        text("SELECT count(*) FROM pg_extension WHERE extname = 'pg_trgm'")
    ).scalar()
    for _, sql in TRGM_INDEXES if has_trgm else FTS_INDEXES:
        conn.execute(text(sql))
    return "pg_trgm" if has_trgm else "fts_simple"


def _clear(conn) -> None:
    if conn.dialect.name == "postgresql":
        _drop_search_indexes(conn)
        conn.execute(text("TRUNCATE star_chunks, star_profiles RESTART IDENTITY"))
    else:
        conn.execute(StarChunk.__table__.delete())
        conn.execute(StarProfile.__table__.delete())


def load(
    engine,
    input_dir: str,
    limit: int | None = None,
    batch: int = 1000,
    log: TextIO | None = None,
) -> dict:
    """Replace star_profiles / star_chunks with the documents in input_dir."""
    t0 = time.time()
    src = Path(input_dir)

    def note(msg: str) -> None:
        if log is not None:
            log.write(f"[{time.time() - t0:7.1f}s] {msg}\n")
            log.flush()

    redirects = read_redirects(src)
    groups = list(read_jsonl(src / "groups.jsonl"))
    genders = {g["title"]: group_gender(g.get("categories") or []) for g in groups}
    now = datetime.now(timezone.utc)
    ids: dict[str, int] = {}
    next_index: dict[int, int] = {}
    stats = {"persons": 0, "groups": 0, "subdocs": 0, "subdocs_skipped": 0}

    with engine.begin() as conn:
        Base.metadata.create_all(conn, tables=TABLES)
        _clear(conn)
        w = Writer(conn, batch)

        def add_doc(rec: dict) -> None:
            fields, rows = build_profile(rec, genders, redirects.get(rec["title"], ()))
            pid = len(ids) + 1
            ids[rec["title"]] = pid
            url = source_url(rec["title"])
            fields.update(id=pid, aliases="\n".join(fields["aliases"]), source_url=url,
                          updated_at=now)
            w.add_profile(fields)
            parts = []
            prof = profile_text(rows)
            if prof:
                parts.append(("프로필", prof))
            parts.extend(doc_chunks(rec.get("text") or ""))
            for i, (sec, content) in enumerate(parts):
                w.add_chunk({"profile_id": pid, "section": sec, "chunk_index": i,
                             "content": content, "source_url": url})
            next_index[pid] = len(parts)
            stats[rec["kind"] + "s"] += 1

        def docs() -> Iterator[dict]:
            yield from groups
            yield from read_jsonl(src / "persons.jsonl")

        for rec in docs():
            if limit is not None and len(ids) >= limit:
                break
            if rec["title"] in ids:
                continue
            add_doc(rec)
            if len(ids) % 2000 == 0:
                note(f"profiles {len(ids)}")
        note(f"profiles done: {len(ids)}")

        for rec in read_jsonl(src / "subdocs.jsonl"):
            pid = ids.get(rec.get("parent") or "")
            if pid is None:
                continue
            suffix = rec["title"].split("/", 1)[1] if "/" in rec["title"] else rec["title"]
            if SKIP_SUBDOC_RE.search(suffix):
                stats["subdocs_skipped"] += 1
                continue
            url = source_url(rec["title"])
            i = next_index[pid]
            for sec, content in doc_chunks(rec.get("text") or "", suffix):
                w.add_chunk({"profile_id": pid, "section": sec, "chunk_index": i,
                             "content": content, "source_url": url})
                i += 1
            next_index[pid] = i
            stats["subdocs"] += 1
        w.flush()
        note(f"rows done: profiles={w.counts['profiles']} chunks={w.counts['chunks']}")

        search_index = None
        if conn.dialect.name == "postgresql":
            for table in ("star_profiles", "star_chunks"):
                conn.execute(text(
                    f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), "
                    f"COALESCE((SELECT max(id) FROM {table}), 0) + 1, false)"
                ))
            search_index = _create_search_indexes(conn)
            note(f"search indexes: {search_index}")

    return {
        **stats,
        "profiles": w.counts["profiles"],
        "chunks": w.counts["chunks"],
        "search_index": search_index,
        "license": LICENSE,
        "license_url": LICENSE_URL,
        "elapsed_sec": round(time.time() - t0, 1),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="python -m scripts.namuwiki.load",
        description="Load extracted star documents into PostgreSQL (replaces star tables).",
    )
    ap.add_argument("--input", required=True, help="folder written by scripts.namuwiki.extract")
    ap.add_argument("--database-url", default=os.environ.get("DATABASE_URL", ""),
                    help="PostgreSQL URL (default: $DATABASE_URL)")
    ap.add_argument("--limit", type=int, default=None, help="load only the first N stars")
    ap.add_argument("--batch", type=int, default=1000, help="rows per INSERT batch")
    ap.add_argument("--quiet", action="store_true", help="no progress log on stderr")
    args = ap.parse_args(argv)

    if not Path(args.input).is_dir():
        print("input folder not found: " + args.input, file=sys.stderr)
        return 2
    try:
        engine = build_engine(args.database_url)
    except ValueError as error:
        print(str(error), file=sys.stderr)
        return 2
    try:
        stats = load(engine, args.input, limit=args.limit, batch=max(1, args.batch),
                     log=None if args.quiet else sys.stderr)
    except Exception as error:
        # never print the URL or the driver message (it may contain the password)
        print("load failed (" + type(error).__name__ + "); nothing was changed.",
              file=sys.stderr)
        return 1
    finally:
        engine.dispose()
    print(json.dumps(stats, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
