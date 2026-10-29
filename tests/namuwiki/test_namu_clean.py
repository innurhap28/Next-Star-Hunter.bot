from scripts.namuwiki.clean import clean, lead_and_body, strip_balanced

DOC = """[[분류:한국 여가수]][[분류:1993년 출생]]
[include(틀:아이유)]
||<|2><bgcolor=#fff> '''출생''' || [[1993년]] [[5월 16일]] (33세) ||
|| [[서울특별시]] [[성동구]] ||
[목차]

== 개요 ==
대한민국의 [[가수|싱어송라이터]]이자 '''배우'''.[* 각주 [[링크]] 안에 [[괄호]]도 있다.]
{{{#!wiki style="color:red"
{{{#fff {{{+1 좋은 날}}}}}}로 알려졌다.}}}
[[https://example.com/news|기사]] 링크와 [[파일:아이유.png|width=100]] 사진.
~~지운 글~~ 남은 글[br]다음 줄
== 활동 ==
=== 2010년 ===
|| 연도 || 제목 || 비고 ||
|| 2010 || 좋은 날 || 3단 고음 ||
데뷔일로부터 계산한 값 (데뷔일로부터 +6,000일, 18주년) 은 지운다.
"""


def test_clean_removes_markup_and_keeps_text():
    out = clean(DOC)

    for left in ("{{{", "}}}", "||", "[[분류:", "[include", "[*", "#!wiki", "[[", "]]", "'''"):
        assert left not in out
    assert "대한민국의 싱어송라이터이자 배우." in out
    assert "좋은 날로 알려졌다." in out
    assert "지운 글" not in out
    assert "남은 글\n다음 줄" in out
    assert "기사" not in out and "example.com" not in out
    assert "2010 | 좋은 날 | 3단 고음" in out
    assert "+6,000일" not in out


def test_clean_drops_lead_but_keeps_headings():
    out = clean(DOC)

    assert out.startswith("== 개요 ==")
    assert "=== 2010년 ===" in out
    assert "성동구" not in out  # infobox goes to the profile instead
    assert "성동구" in clean(DOC, drop_lead=False)


def test_document_without_heading_keeps_everything():
    assert clean("그냥 [[문장]]이다.") == "그냥 문장이다."


def test_links_with_brackets_in_target_and_label():
    out = clean("== 출연 ==\n[[IDOL [아이돌 : The Coup]]] 출연, "
                "[[https://youtu.be/x|[MV] 노래]] 끝")
    assert out == "== 출연 ==\nIDOL [아이돌 : The Coup] 출연, 끝"


def test_table_inside_one_line_box_becomes_text():
    out = clean('== 여담 ==\n- 표지 모델 {{{#!wiki style="width:500px" '
                "||<tablewidth=100%><:> 사진 || ||<bgcolor=#fff> 설명 ||}}}")
    assert "||" not in out and "#!wiki" not in out and "<bgcolor" not in out
    assert "사진 | 설명" in out


def test_strip_balanced_handles_nested_brackets():
    assert strip_balanced("가[* 각주 [[링크]] 끝]나", "[*") == "가나"


def test_lead_and_body_split_at_first_heading():
    lead, body = lead_and_body("앞\n== 제목 ==\n뒤")
    assert lead == "앞\n" and body.startswith("== 제목 ==")
