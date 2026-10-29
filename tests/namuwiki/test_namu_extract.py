import json
from pathlib import Path

from scripts.namuwiki.extract import main, run
from scripts.namuwiki.rules import GROUP_CATEGORIES

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "namuwiki" / "namu_sample.json"


def read_jsonl(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f]


def test_cli_writes_jsonl_files(tmp_path, capsys):
    code = main(["--dump", str(FIXTURE), "--out", str(tmp_path), "--quiet"])

    assert code == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed["written"] == {"persons": 3, "groups": 2, "subdocs": 1, "aliases": 2}

    persons = read_jsonl(tmp_path / "persons.jsonl")
    assert [p["title"] for p in persons] == ["간미연", "잭슨(GOT7)", "박은태"]
    jackson = persons[1]
    assert jackson["kind"] == "person"
    assert jackson["signals"] == ["S2", "S3"]
    assert "GOT7/멤버" in jackson["categories"]
    assert jackson["text"].startswith("[[분류:")

    groups = read_jsonl(tmp_path / "groups.jsonl")
    assert {g["title"] for g in groups} == {"베이비복스", "GOT7"}
    for g in groups:
        assert g["kind"] == "group"
        assert GROUP_CATEGORIES & set(g["categories"])

    subdocs = read_jsonl(tmp_path / "subdocs.jsonl")
    assert [(s["title"], s["parent"], s["parent_kind"]) for s in subdocs] == [
        ("GOT7/응원법", "GOT7", "group")
    ]

    aliases = read_jsonl(tmp_path / "aliases.jsonl")
    assert {(a["title"], a["target"]) for a in aliases} == {
        ("갓세븐", "GOT7"),
        ("왕잭슨", "잭슨(GOT7)"),
    }

    stats = json.loads((tmp_path / "stats.json").read_text(encoding="utf-8"))
    assert stats["read"]["records"] == 14
    assert stats["category_pages"] == 1


def test_known_group_adds_member_and_subdoc(tmp_path):
    stats = run(str(FIXTURE), str(tmp_path), known_groups=["TWICE"], chunk_size=1024)

    titles = [p["title"] for p in read_jsonl(tmp_path / "persons.jsonl")]
    assert "모모(TWICE)" in titles
    assert stats["written"]["persons"] == 4


def test_small_chunks_give_same_output(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    run(str(FIXTURE), str(a))
    run(str(FIXTURE), str(b), chunk_size=7)

    for name in ["persons", "groups", "subdocs", "aliases"]:
        assert (a / f"{name}.jsonl").read_bytes() == (b / f"{name}.jsonl").read_bytes()
