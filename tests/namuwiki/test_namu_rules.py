import json
from pathlib import Path

from scripts.namuwiki import categories as C
from scripts.namuwiki.rules import judge_person, person_signals, select

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "namuwiki" / "namu_sample.json"


def fixture_docs():
    records = json.loads(FIXTURE.read_text(encoding="utf-8"))
    parents = {
        C.category_name(r["title"]): C.parent_categories(r["text"])
        for r in records
        if C.namespace_of(r["title"]) == "분류"
    }
    docs = {}
    for r in records:
        t = r["title"]
        if C.namespace_of(t) != C.DOCUMENT or "/" in t or C.redirect_target(r["text"]):
            continue
        docs[t] = C.effective_categories(t, C.page_categories(r["text"]), parents)
    return docs


# --- categories


def test_page_categories_strip_blur_pipe_and_duplicates():
    text = (
        "[[분류:한국 여가수]][[분류: 1993년 출생 #blur]]\n"
        "[[분류:한국 여가수]][[분류:아이유|정렬]]"
    )

    assert C.page_categories(text) == ["한국 여가수", "1993년 출생", "아이유"]


def test_parent_categories_skip_listing_and_piped_links():
    text = (
        "[[분류:TWICE/멤버]][[분류:일본 여가수]]\n본문 [[분류:정렬용|X]]\n"
        "== 하위 분류 ==\n* [[분류:모모(TWICE)/사진]]\n[[분류:목록 안]]"
    )

    assert C.parent_categories(text) == ["TWICE/멤버", "일본 여가수"]


def test_effective_categories_expand_own_name_category_once():
    parents = {"나연": ["한국 여가수", "TWICE/멤버"], "TWICE/멤버": ["TWICE"]}

    got = C.effective_categories("나연", ["나연"], parents)

    assert got == {"나연", "한국 여가수", "TWICE/멤버"}
    assert C.effective_categories("다른 문서", ["나연"], parents) == {"나연"}


def test_namespace_and_redirect():
    assert C.namespace_of("분류:나연") == "분류"
    assert C.namespace_of("틀:TWICE") == "틀"
    assert C.namespace_of("Re:제로부터 시작하는 이세계 생활") == C.DOCUMENT
    assert C.redirect_target("  #REDIRECT 방탄소년단\n") == "방탄소년단"
    assert C.redirect_target("[[분류:가수]] 본문") is None


# --- selection on the fixture


def test_fixture_groups_and_persons():
    sel = select(fixture_docs())

    assert sel.groups == {"베이비복스", "GOT7"}
    assert sel.persons == {
        "간미연": ["S1", "S2", "S3"],
        "잭슨(GOT7)": ["S2", "S3"],
        "박은태": ["S1"],
    }


def test_fixture_non_stars_are_not_selected():
    sel = select(fixture_docs())

    for title in ["Killer(베이비복스)", "제니", "브라이언 드 키어스매커", "에비하라 츠즈미"]:
        assert sel.kind_of(title) is None


def test_self_category_member_needs_group_page():
    docs = fixture_docs()
    assert "아이돌 댄서" in docs["모모(TWICE)"]  # came from the page 분류:모모(TWICE)

    assert "모모(TWICE)" not in select(docs).persons
    assert select(docs, known_groups={"TWICE"}).persons["모모(TWICE)"] == ["S2", "S3"]


# --- single rules


def judge(cats, groups=(), agencies=()):
    cats = set(cats)
    sig = person_signals(cats, set(groups), set(agencies))
    return sig, judge_person(cats, sig)


def test_album_with_singer_category_is_not_a_person():
    assert judge(["한국 여가수", "2001년 음반"])[1] == "drop_not_person"


def test_weak_job_with_other_profession_is_dropped():
    sig, reason = judge(["대한민국의 남성 방송인", "1980년 출생", "대한민국의 야구 선수"])
    assert reason == "drop_weak_s1_with_other_profession"

    sig, reason = judge(["대한민국의 남성 방송인", "대한민국의 야구 선수", "KBS 연예대상 수상자"])
    assert reason is None


def test_agency_signal_needs_debut_year():
    agencies = {"안테나"}
    assert judge(["안테나 소속 아티스트", "1990년 출생"], agencies=agencies)[1] == (
        "drop_S4_without_debut"
    )

    sig, reason = judge(["안테나 소속 아티스트", "1990년 출생", "2015년 데뷔"], agencies=agencies)
    assert sig == ["S4"]
    assert reason is None


def test_meme_category_alone_is_not_enough():
    assert judge(["인터넷 밈/배우/대한민국", "미국 남배우"])[1] == "drop_S5_only"


def test_foreign_idol_without_korean_signal_is_dropped():
    assert judge(["아이돌 보컬", "일본 여가수", "2000년 출생"])[1] == "drop_no_korean_signal"
