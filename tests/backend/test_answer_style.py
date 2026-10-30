"""Answer style: one random star, the title line, and the casual prompt."""
import json
import random
from types import SimpleNamespace

import httpx
import pytest
from test_chat_api import ACCOUNT, FakeAI
from test_star_search import chat_client, chat_engine, engine  # noqa: F401

from app.services import chat as chat_service
from app.services.ai_client import SYSTEM_PROMPT, build_messages
from app.services.chat import pick_star
from app.services.star_search import (
    StarSearchResult,
    display_name,
    remove_title_lines,
    search_stars,
    strip_title_line,
    title_line,
)


def hit(title, **flags):
    return {"title": title, "aliases": [], "snippets": [], **flags}


def test_pick_is_deterministic_with_a_seeded_rng():
    found = StarSearchResult(stars=[hit("가"), hit("나"), hit("다"), hit("라")],
                             missing_keywords=["안경"], conditions=["기준"])
    first = pick_star(found, random.Random(7))
    again = pick_star(found, random.Random(7))
    assert len(first.stars) == 1 and first.stars == again.stars
    assert first.stars[0]["title"] == random.Random(7).choice(["가", "나", "다", "라"])
    assert first.missing_keywords == ["안경"] and first.conditions == ["기준"]


def test_pick_prefers_keyword_matches_and_skips_the_anchor():
    found = StarSearchResult(stars=[hit("TWICE", anchor=True), hit("모모"),
                                    hit("나연", matched=True)])
    for seed in range(10):
        assert pick_star(found, random.Random(seed)).stars[0]["title"] == "나연"
    alone = StarSearchResult(stars=[hit("TWICE", anchor=True)])
    assert pick_star(alone, random.Random(0)).stars[0]["title"] == "TWICE"
    assert pick_star(StarSearchResult(), random.Random(0)).stars == []


def test_search_marks_group_and_compared_star_as_anchor(engine):  # noqa: F811
    group = search_stars(engine, "트와이스 멤버 알려줘")
    assert group.stars[0]["anchor"] and not any(s["anchor"] for s in group.stars[1:])
    similar = search_stars(engine, "아이유랑 비슷한 가수")
    assert similar.stars[0]["title"] == "아이유" and similar.stars[0]["anchor"]
    assert pick_star(similar, random.Random(0)).stars[0]["title"] != "아이유"


@pytest.mark.parametrize("title, expected", [
    ("산들(가수)", "˗ˋˏ 산들 ˎˊ˗"),
    ("모모(TWICE)", "˗ˋˏ 모모 ˎˊ˗"),
    ("아이유", "˗ˋˏ 아이유 ˎˊ˗"),
])
def test_title_line_drops_the_parenthesized_part(title, expected):
    assert title_line(title) == expected


def test_display_name_removes_only_the_trailing_disambiguation():
    assert display_name("(여자)아이들") == "(여자)아이들"
    assert display_name("(괄호)") == "(괄호)"


def test_model_written_title_lines_are_removed():
    text = "˗ˋˏ 산들 ˎˊ˗\n\n산들 어때? 목소리 좋아 🎤\n# 산들\n끝!"
    assert remove_title_lines(text) == "산들 어때? 목소리 좋아 🎤\n끝!"
    assert remove_title_lines("그냥 답") == "그냥 답"


def test_history_drops_the_title_line_and_keeps_the_body():
    saved = "˗ˋˏ 산들 ˎˊ˗\n\n산들 추천해!\n\n출처: 나무위키(CC BY-NC-SA 2.0 KR) - 산들(가수)"
    messages = build_messages([SimpleNamespace(question="q", answer=saved)], "n")
    assert messages[1] == {"role": "assistant", "content": "산들 추천해!"}
    assert strip_title_line("산들 추천해!") == "산들 추천해!"


def test_prompt_asks_for_casual_tone_one_star_and_few_emoji():
    assert "반말" in SYSTEM_PROMPT
    assert "한 명" in SYSTEM_PROMPT
    assert "이모지" in SYSTEM_PROMPT and "문장마다 붙이지는 마" in SYSTEM_PROMPT
    assert "제목 줄" in SYSTEM_PROMPT


def ask(message, reply, monkeypatch, seed=1):
    monkeypatch.setattr(chat_service, "rng", random.Random(seed))
    fake = FakeAI()
    fake.handler = lambda request: httpx.Response(
        200, json={"content": [{"type": "text", "text": reply}]})
    e = chat_engine()
    client, _ = chat_client(e, fake)
    with client:
        client.post("/api/auth/register", json=ACCOUNT)
        client.post("/api/auth/login", json=ACCOUNT)
        r = client.post("/api/chat", json={"message": message})
    e.dispose()
    return r.json()["answer"], json.loads(fake.requests[-1].content)["system"]


def test_chat_sends_only_the_picked_star_with_a_seeded_rng(monkeypatch):
    reply = "˗ˋˏ 아무개 ˎˊ˗\n신인걸 추천해! 키가 커 ✨"
    answer, system = ask("2020년에 데뷔한 걸그룹 멤버 중에 키 큰 사람", reply, monkeypatch)
    expected = random.Random(1).choice(["신인걸", "신인걸2"])
    assert "\n1. " + expected + " (" in system and "\n2. " not in system
    assert answer == ("˗ˋˏ " + expected + " ˎˊ˗\n\n신인걸 추천해! 키가 커 ✨\n\n"
                      "출처: 나무위키(CC BY-NC-SA 2.0 KR) - " + expected)


def test_chat_without_hits_has_no_title_line(monkeypatch):
    answer, _ = ask("아무것도없는단어", "자료에서 못 찾았어 😅", monkeypatch)
    assert answer == "자료에서 못 찾았어 😅"
