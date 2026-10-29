from scripts.namuwiki.profile import (
    birthplace_from,
    build_profile,
    profile_rows,
    profile_text,
)

PERSON = """[[분류:나연]]
||<-2> '''나연''' ||
||<|2> '''출생''' || [[1995년]] [[9월 22일]] (31세) ||
|| [[서울특별시]] [[강동구]] ||
|| '''본명''' || 임나연 (林娜璉) ||
|| '''신체''' || 163cm, A형 ||
|| '''소속사''' || [[JYP엔터테인먼트]] (2010~) ||
|| '''데 뷔''' || [[2015년]] [[10월 20일]] ||
|| '''가족''' || 아버지, 어머니 ||
|| '''거주지''' || 서울특별시 어딘가동 ||
|| 5기(1987) || 내비게이션 박스 ||
== 개요 ==
대한민국의 가수.
"""


def record(title, kind, categories, text=""):
    return {"title": title, "kind": kind, "categories": categories, "text": text}


def test_profile_rows_follow_row_span_and_skip_unknown_labels():
    rows = dict(profile_rows(PERSON))

    assert rows["출생"] == "1995년 9월 22일 / 서울특별시 강동구"
    assert rows["본명"] == "임나연 (林娜璉)"
    assert rows["데뷔"] == "2015년 10월 20일"
    assert "5기(1987)" not in rows


def test_person_profile_from_categories_and_infobox():
    cats = ["TWICE/멤버", "1995년 출생", "강동구 출신 인물"]
    fields, rows = build_profile(record("나연", "person", cats, PERSON),
                                 group_genders={"TWICE": "F"}, redirects=["임나연(가수)"])

    assert fields["gender"] == "F"  # from the girl group
    assert fields["group_name"] == "TWICE"
    assert fields["birth_year"] == 1995
    assert fields["debut_year"] == 2015
    assert fields["birthplace"] == "서울특별시 강동구"
    assert fields["agency"] == "JYP엔터테인먼트"
    assert fields["height_cm"] == 163.0
    assert fields["aliases"] == ["임나연", "임나연(가수)"]


def test_profile_text_leaves_out_family_and_address():
    _, rows = build_profile(record("나연", "person", [], PERSON))
    text = profile_text(rows)
    assert "출생: 1995년 9월 22일 / 서울특별시 강동구" in text
    assert "가족" not in text and "거주지" not in text
    assert "31세" not in text


def test_gender_conflict_stays_empty():
    fields, _ = build_profile(record("누군가", "person", ["한국 남가수", "한국 여배우"]))
    assert fields["gender"] is None


def test_group_profile():
    fields, _ = build_profile(record("TWICE", "group", ["대한민국의 걸그룹", "2015년 데뷔"]))
    assert fields["kind"] == "group"
    assert fields["gender"] == "F"
    assert fields["debut_year"] == 2015
    assert fields["birth_year"] is None and fields["group_name"] is None


def test_birthplace_skips_dates_and_foreign_places_stay():
    assert birthplace_from("1990년 1월 1일 / 부산광역시 해운대구") == "부산광역시 해운대구"
    assert birthplace_from("1994년 3월 28일 / 영국령 홍콩 사전구") == "영국령 홍콩 사전구"
    assert birthplace_from("1990년 1월 1일") is None


def test_unreliable_values_are_dropped():
    text = "|| '''신체''' || 1.7cm ||\n|| '''소속사''' || 없음 ||\n== 개요 ==\n"
    fields, _ = build_profile(record("가수", "person", [], text))
    assert fields["height_cm"] is None
    assert fields["agency"] is None
