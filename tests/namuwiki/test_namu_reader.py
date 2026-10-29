import json
from collections import Counter
from pathlib import Path

import pytest

from scripts.namuwiki.reader import DumpFormatError, iter_records

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "namuwiki" / "namu_sample.json"


def rec(title, text):
    return {"namespace": 0, "title": title, "text": text, "contributors": []}


def dump_text(records):
    # same layout as the real dump: one line, no spaces between records
    return "[" + ",".join(json.dumps(r, ensure_ascii=False) for r in records) + "]"


def write(tmp_path, text, name="dump.json"):
    p = tmp_path / name
    p.write_bytes(text.encode("utf-8"))
    return str(p)


SAMPLE = [
    rec("아이유", "[[분류:한국 여가수]]\n'''아이유'''는 대한민국의 가수다."),
    rec("따옴표", 'He said "hi" and {"namespace": 0, "title": "가짜"} stays text'),
    rec("이모지", "🎤 노래 ✨ 한글과 emoji, 탭\t줄바꿈\n끝"),
    rec("BTS", "#redirect 방탄소년단\n"),
]


@pytest.mark.parametrize("chunk_size", [1, 2, 3, 5, 7, 16, 1 << 20])
def test_reads_all_records_with_any_chunk_size(tmp_path, chunk_size):
    path = write(tmp_path, dump_text(SAMPLE))

    got = list(iter_records(path, chunk_size=chunk_size))

    assert got == SAMPLE


def test_escaped_quotes_and_unicode_survive(tmp_path):
    path = write(tmp_path, dump_text(SAMPLE))

    got = {r["title"]: r["text"] for r in iter_records(path, chunk_size=4)}

    assert '"hi"' in got["따옴표"]
    assert '{"namespace": 0' in got["따옴표"]
    assert got["이모지"].startswith("🎤")


def test_ascii_escaped_dump_is_read(tmp_path):
    text = "[" + ",".join(json.dumps(r, ensure_ascii=True) for r in SAMPLE) + "]"
    path = write(tmp_path, text)

    assert list(iter_records(path, chunk_size=3)) == SAMPLE


def test_whitespace_between_records(tmp_path):
    text = " [\n" + " ,\n".join(json.dumps(r, ensure_ascii=False) for r in SAMPLE) + "\n]\n"
    path = write(tmp_path, text)

    assert list(iter_records(path, chunk_size=5)) == SAMPLE


def test_empty_array(tmp_path):
    path = write(tmp_path, "[]")

    assert list(iter_records(path)) == []


def test_not_an_array_raises(tmp_path):
    path = write(tmp_path, '{"namespace": 0}')

    with pytest.raises(DumpFormatError):
        list(iter_records(path))


def test_oversized_record_is_skipped(tmp_path):
    records = [rec("앞", "a"), rec("큰 문서", "가" * 5000), rec("뒤", "b")]
    path = write(tmp_path, dump_text(records))
    stats = Counter()

    got = list(iter_records(path, chunk_size=64, max_record_chars=1000, stats=stats))

    assert [r["title"] for r in got] == ["앞", "뒤"]
    assert stats["oversized_skipped"] == 1
    assert stats["records"] == 2


def test_broken_record_is_skipped(tmp_path):
    good = [json.dumps(rec("앞", "a"), ensure_ascii=False), json.dumps(rec("뒤", "b"))]
    broken = '{"namespace": 0, "title": "깨짐", "text": "닫히지 않은 문자열}'
    path = write(tmp_path, "[" + good[0] + "," + broken + "," + good[1] + "]")
    stats = Counter()

    got = list(iter_records(path, chunk_size=8, stats=stats))

    assert [r["title"] for r in got] == ["앞", "뒤"]
    assert stats["decode_errors"] == 1


def test_fixture_records():
    titles = [r["title"] for r in iter_records(str(FIXTURE), chunk_size=4096)]

    assert len(titles) == 14
    assert titles[0] == "간미연"
    assert "분류:모모(TWICE)" in titles
    assert "GOT7/응원법" in titles
