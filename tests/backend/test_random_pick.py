"""Random pick (#64): '오늘의 랜덤 스타' takes one random person from the star data."""
import json

import httpx
import pytest
from sqlalchemy import create_engine
from test_chat_api import ACCOUNT, FakeAI
from test_follow_up import REPLY, SOURCE, picked, talk
from test_star_search import chat_client, chat_engine, engine  # noqa: F401

from app.models import StarProfile
from app.services.ai_client import RANDOM_PICK_NOTE, SYSTEM_PROMPT
from app.services.chat import follow_up_mode
from app.services.star_search import RANDOM_CONDITION, is_random_request, random_star

PRESET = "오늘의 랜덤 스타를 추천해줘"  # the suggestion button on the chat page
PERSONS = {"모모(TWICE)", "나연", "부산돌", "부산배우", "아이유", "솔로가수", "신인걸", "신인걸2"}


@pytest.mark.parametrize("message", [
    PRESET, "아무나 추천해줘", "아무 스타나 한 명", "무작위로 골라줘", "랜덤으로 한명 골라줘",
    "오늘의 스타 추천해줘", "골라줘", "아무나 랜덤으로 뽑아줘!",
])
def test_random_request(message):
    assert is_random_request(message)


@pytest.mark.parametrize("message", [
    "랜덤 아이돌 추천해줘", "부산 출신 아무나", "트와이스에서 골라줘", "안경 쓴 사람 골라줘",
    "오늘 기분이 우울해", "다른 사람 추천해줘", "아이유랑 비슷한 사람 아무나",
])
def test_request_with_conditions_is_not_random(message):
    assert not is_random_request(message)


def test_random_request_is_its_own_follow_up_mode():
    assert follow_up_mode(PRESET, "부산돌") == "random"
    assert follow_up_mode("골라줘", None) == "random"


def test_random_star_picks_one_person(engine):  # noqa: F811
    for _ in range(20):
        found = random_star(engine)
        assert len(found.stars) == 1 and found.stars[0]["title"] in PERSONS
        assert found.conditions == [RANDOM_CONDITION]
        assert found.stars[0]["snippets"]  # profile chunk for the reference block


def test_random_star_prefers_people_with_a_group_or_debut_year(engine):  # noqa: F811
    with engine.begin() as conn:
        conn.execute(StarProfile.__table__.insert(),
                     [dict(id=10, title="무명", kind="person", aliases="",
                           source_url="https://namu.wiki/w/무명")])
    assert all(random_star(engine).stars[0]["title"] != "무명" for _ in range(30))
    # the others are already recommended: the less known one is still a pick
    assert random_star(engine, tuple(PERSONS)).stars[0]["title"] == "무명"
    assert random_star(engine, tuple(PERSONS) + ("무명",)).stars == []


def test_random_star_without_data_never_raises(caplog):
    empty = chat_engine(with_rows=False)
    assert random_star(empty).stars == []
    empty.dispose()
    broken = create_engine("sqlite://")  # no tables
    assert random_star(broken).stars == []
    assert "star_search_failure" in caplog.text
    broken.dispose()


@pytest.mark.parametrize("seed", range(3))
def test_preset_button_gets_a_random_star(monkeypatch, seed):
    [(answer, system)] = talk([PRESET], monkeypatch, seed)
    star = picked(answer)
    assert star in PERSONS
    assert answer.startswith("˗ˋˏ ") and answer.endswith(SOURCE + star)
    assert RANDOM_PICK_NOTE in system and RANDOM_CONDITION in system
    assert system.index(RANDOM_PICK_NOTE) < system.index("<참고자료>\n")


def test_another_person_after_a_random_pick_is_random_again(monkeypatch):
    answers = talk([PRESET, "그 사람 키 몇이야?", "다른 사람 추천해줘", "다른 사람",
                    "걔 말고"], monkeypatch)
    stars = [picked(a) for a, _ in answers]
    assert stars[0] == stars[1]  # a question about the star keeps it
    assert len({stars[0], *stars[2:]}) == 4 and set(stars) <= PERSONS
    assert all(RANDOM_PICK_NOTE in system for _, system in answers[2:])
    assert RANDOM_PICK_NOTE not in answers[1][1]


def test_random_picks_skip_stars_already_recommended(monkeypatch):
    answers = talk([PRESET, "아무나 추천해줘", "랜덤으로 골라줘", "오늘의 스타 추천해줘",
                    "무작위로 골라줘"], monkeypatch)
    stars = [picked(a) for a, _ in answers]
    assert len(set(stars)) == 5 and set(stars) <= PERSONS


def test_another_person_with_new_conditions_after_a_random_pick_searches(monkeypatch):
    answers = talk([PRESET, "다른 사람 중에 2020년에 데뷔한 걸그룹 멤버 추천해줘"], monkeypatch)
    assert picked(answers[1][0]) in ("신인걸", "신인걸2")
    assert RANDOM_PICK_NOTE not in answers[1][1]


def test_random_request_without_star_data_answers_as_before():
    e = chat_engine(with_rows=False)
    fake = FakeAI()
    fake.handler = lambda request: httpx.Response(
        200, json={"content": [{"type": "text", "text": REPLY}]})
    client, _ = chat_client(e, fake)
    with client:
        client.post("/api/auth/register", json=ACCOUNT)
        client.post("/api/auth/login", json=ACCOUNT)
        r = client.post("/api/chat", json={"message": PRESET})
    assert r.status_code == 200 and r.json()["answer"] == REPLY
    system = json.loads(fake.requests[-1].content)["system"]
    assert system == SYSTEM_PROMPT  # no reference block and no random note
    e.dispose()
