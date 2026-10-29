import os
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool

from scripts.namuwiki.extract import run
from scripts.namuwiki.load import load, main, source_url

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "namuwiki" / "namu_sample.json"


@pytest.fixture
def derived(tmp_path):
    out = tmp_path / "derived"
    run(str(FIXTURE), str(out), known_groups=["TWICE"])
    return out


@pytest.fixture
def engine():
    e = create_engine("sqlite://", connect_args={"check_same_thread": False},
                      poolclass=StaticPool)
    yield e
    e.dispose()


def rows(engine, sql):
    with engine.connect() as c:
        return [dict(r._mapping) for r in c.execute(text(sql))]


def test_load_fills_profiles_and_chunks(engine, derived):
    stats = load(engine, str(derived))

    assert stats["groups"] == 2 and stats["persons"] == 4
    assert stats["profiles"] == 6
    assert stats["subdocs_skipped"] == 1  # GOT7/응원법
    assert stats["license"] == "CC BY-NC-SA 2.0 KR"

    profiles = {p["title"]: p for p in rows(engine, "SELECT * FROM star_profiles")}
    assert set(profiles) == {"베이비복스", "GOT7", "간미연", "잭슨(GOT7)", "박은태", "모모(TWICE)"}
    mi = profiles["간미연"]
    assert (mi["kind"], mi["gender"], mi["birth_year"], mi["debut_year"]) == ("person", "F", 1982,
                                                                              1997)
    assert mi["group_name"] == "베이비복스"
    assert mi["height_cm"] == 170.0
    assert mi["birthplace"].startswith("서울특별시 마포구")
    assert profiles["GOT7"]["gender"] == "M"
    assert "갓세븐" in profiles["GOT7"]["aliases"].split("\n")
    assert "왕잭슨" in profiles["잭슨(GOT7)"]["aliases"].split("\n")
    assert profiles["간미연"]["source_url"] == "https://namu.wiki/w/%EA%B0%84%EB%AF%B8%EC%97%B0"


def test_chunks_are_numbered_per_profile_and_clean(engine, derived):
    load(engine, str(derived))
    chunks = rows(engine, "SELECT * FROM star_chunks ORDER BY profile_id, chunk_index")

    assert chunks
    by_profile = {}
    for c in chunks:
        by_profile.setdefault(c["profile_id"], []).append(c["chunk_index"])
        assert 0 < len(c["content"]) <= 1000
        assert c["section"]
        assert c["source_url"].startswith("https://namu.wiki/w/")
        for left in ("{{{", "||", "[[분류:", "[include", "[*"):
            assert left not in c["content"]
    for indexes in by_profile.values():
        assert indexes == list(range(len(indexes)))
    assert len(by_profile) == 6


def test_reload_replaces_rows(engine, derived):
    first = load(engine, str(derived))
    before = rows(engine, "SELECT title, id FROM star_profiles ORDER BY id")
    second = load(engine, str(derived))

    assert first["chunks"] == second["chunks"]
    assert rows(engine, "SELECT title, id FROM star_profiles ORDER BY id") == before
    assert rows(engine, "SELECT count(*) AS n FROM star_chunks")[0]["n"] == second["chunks"]


def test_limit_loads_first_stars_only(engine, derived):
    stats = load(engine, str(derived), limit=2, batch=1)
    assert stats["profiles"] == 2
    assert rows(engine, "SELECT count(*) AS n FROM star_profiles")[0]["n"] == 2


def test_subdocs_attach_to_parent(engine, tmp_path):
    out = tmp_path / "in"
    out.mkdir()
    (out / "persons.jsonl").write_text(
        '{"title": "가수", "kind": "person", "categories": [], "text": "== 개요 ==\\n가수다."}\n',
        encoding="utf-8")
    (out / "subdocs.jsonl").write_text(
        '{"title": "가수/여담", "kind": "subdoc", "parent": "가수", "parent_kind": "person",'
        ' "categories": [], "text": "== 습관 ==\\n노래를 흥얼거린다."}\n', encoding="utf-8")

    stats = load(engine, str(out))

    assert stats["subdocs"] == 1
    chunks = rows(engine, "SELECT section, chunk_index, source_url FROM star_chunks"
                          " ORDER BY chunk_index")
    assert [(c["section"], c["chunk_index"]) for c in chunks] == [("개요", 0), ("여담 > 습관", 1)]
    assert chunks[1]["source_url"] == source_url("가수/여담")


def test_source_url_keeps_subdocument_slash():
    assert source_url("아이유/여담") == (
        "https://namu.wiki/w/%EC%95%84%EC%9D%B4%EC%9C%A0/%EC%97%AC%EB%8B%B4")


def test_cli_rejects_non_postgres_url(derived, capsys):
    code = main(["--input", str(derived), "--database-url", "sqlite:///secret.db", "--quiet"])
    assert code == 2
    assert "secret" not in capsys.readouterr().err


def test_real_postgres_load():
    url = os.getenv("TEST_POSTGRES_URL")
    if not url:
        pytest.skip("TEST_POSTGRES_URL is not set; real PostgreSQL is unverified")
    from app.database import build_engine

    schema = "nsh_test_" + uuid4().hex
    admin = build_engine(url)
    with admin.begin() as c:
        c.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_engine(admin.url, connect_args={"options": f"-csearch_path={schema},public"})
    try:
        tmp = Path(os.getenv("TMPDIR", "/tmp")) / schema
        run(str(FIXTURE), str(tmp), known_groups=["TWICE"])
        first = load(engine, str(tmp))
        second = load(engine, str(tmp))
        assert first["profiles"] == second["profiles"] == 6
        assert second["search_index"] in ("pg_trgm", "fts_simple")
        with engine.connect() as c:
            assert c.execute(text("SELECT count(*) FROM star_chunks")).scalar() == second["chunks"]
    finally:
        engine.dispose()
        with admin.begin() as c:
            c.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()
