"""Streaming reader for the Namu Wiki dump.

The dump is one JSON array on a single line (about 30GB), so json.load is not an option.
We read fixed-size chunks, decode UTF-8 incrementally and pull one record at a time with
json.JSONDecoder.raw_decode. Consumed text is dropped, so memory stays around
chunk_size + the largest record.

Every record starts with the text '{"namespace": '. A raw '"' inside a JSON string is always
escaped, so this text never shows up inside a record. We only use it to resync after a broken
record and to skip records larger than max_record_chars.
"""

from __future__ import annotations

import codecs
import json
from collections import Counter
from collections.abc import Iterator
from typing import BinaryIO

MARKER = '{"namespace": '
DEFAULT_CHUNK_SIZE = 16 << 20  # bytes per read
DEFAULT_MAX_RECORD_CHARS = 64 << 20  # the dump has one broken record of ~546M chars

_WS = " \t\r\n"


class DumpFormatError(ValueError):
    pass


class _Buffer:
    """Text window over the file: buf[pos:] is what has not been consumed yet."""

    def __init__(self, f: BinaryIO, chunk_size: int):
        self.f = f
        self.chunk_size = chunk_size
        self.utf8 = codecs.getincrementaldecoder("utf-8")()
        self.buf = ""
        self.pos = 0
        self.eof = False

    def read_more(self) -> bool:
        """Append the next chunk (dropping consumed text). False at end of file."""
        if self.eof:
            return False
        data = self.f.read(self.chunk_size)
        if data:
            text = self.utf8.decode(data)
        else:
            self.eof = True
            text = self.utf8.decode(b"", final=True)
        self.buf = self.buf[self.pos:] + text
        self.pos = 0
        return bool(data)

    def skip_ws(self) -> bool:
        """Move pos to the next non-space char. False at end of file."""
        while True:
            buf, pos = self.buf, self.pos
            while pos < len(buf) and buf[pos] in _WS:
                pos += 1
            self.pos = pos
            if pos < len(buf):
                return True
            if not self.read_more():
                return False

    def skip_record(self) -> bool:
        """Jump to the next record start after pos. False if there is none."""
        start = self.pos + 1
        while True:
            nxt = self.buf.find(MARKER, start)
            if nxt != -1:
                self.pos = nxt
                return True
            # keep only a tail that could hold the start of a split marker
            self.pos = max(start, len(self.buf) - len(MARKER) + 1)
            if not self.read_more():
                self.pos = len(self.buf)
                return False
            start = 0

    def compact(self) -> None:
        if self.pos > self.chunk_size:
            self.buf = self.buf[self.pos:]
            self.pos = 0


def iter_records(
    path: str,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    max_record_chars: int = DEFAULT_MAX_RECORD_CHARS,
    stats: Counter | None = None,
) -> Iterator[dict]:
    """Yield each record (dict) of the JSON array in `path`, in file order.

    stats (optional Counter) gets: records, decode_errors, oversized_skipped.
    """
    if stats is None:
        stats = Counter()
    decoder = json.JSONDecoder()

    with open(path, "rb") as f:
        b = _Buffer(f, chunk_size)
        if not b.skip_ws() or b.buf[b.pos] != "[":
            raise DumpFormatError("dump must start with a JSON array")
        b.pos += 1

        while True:
            if not b.skip_ws():
                raise DumpFormatError("unexpected end of file (missing ']')")
            ch = b.buf[b.pos]
            if ch == ",":
                b.pos += 1
                continue
            if ch == "]":
                return

            obj = _decode_one(b, decoder, max_record_chars, stats)
            if obj is not None:
                stats["records"] += 1
                yield obj
            elif b.pos >= len(b.buf) and b.eof:
                return
            b.compact()


def _decode_one(b: _Buffer, decoder: json.JSONDecoder, max_chars: int, stats: Counter):
    """Decode the record at b.pos. Returns None (and moves past it) if it is skipped."""
    while True:
        try:
            obj, end = decoder.raw_decode(b.buf, b.pos)
        except json.JSONDecodeError:
            if b.buf.find(MARKER, b.pos + 1) != -1:
                # the next record is already in the buffer, so this one is broken
                stats["decode_errors"] += 1
                b.skip_record()
                return None
            if len(b.buf) - b.pos > max_chars:
                stats["oversized_skipped"] += 1
                b.skip_record()
                return None
            if not b.read_more():
                stats["decode_errors"] += 1  # broken tail
                b.pos = len(b.buf)
                return None
            continue
        b.pos = end
        if not isinstance(obj, dict):
            stats["decode_errors"] += 1
            return None
        return obj
