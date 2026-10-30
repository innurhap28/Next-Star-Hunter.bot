"""Follow-up questions: keep the star just recommended, or pick another one on request."""
import json
import random
from types import SimpleNamespace

import httpx
import pytest
from sqlalchemy import create_engine, update
from test_chat_api import ACCOUNT, FakeAI
from test_star_search import chat_client, chat_engine, engine  # noqa: F401

from app.models import ChatLog, Conversation, StarChunk, User
from app.services import chat as chat_service
from app.services.ai_client import SYSTEM_PROMPT
from app.services.chat import follow_up_mode
from app.services.star_search import answered_star, find_star, is_star_name

SOURCE = "출처: 나무위키(CC BY-NC-SA 2.0 KR) - "
REPLY = "응 알려줄게 ✨"
NEW_GIRLS = "2020년에 데뷔한 걸그룹 멤버 중에 키 큰 사람"


def talk(messages, monkeypatch, seed=1, before=None):
    """Send the messages in order in one conversation; [(answer, system prompt)] per message."""
    monkeypatch.setattr(chat_service, "rng", random.Random(seed))
    fake = FakeAI()
    fake.handler = lambda request: httpx.Response(
        200, json={"content": [{"type": "text", "text": REPLY}]})
    e = chat_engine()
    client, factory = chat_client(e, fake)
    out = []
    conversation_id = None
    with client:
        client.post("/api/auth/register", json=ACCOUNT)
        client.post("/api/auth/login", json=ACCOUNT)
        if before:
            with factory() as db:
                user = db.query(User).one()
                room = Conversation(user_id=user.id, title="before")
                db.add(room)
                db.flush()
                conversation_id = room.id
                for question, answer in before:
                    db.add(ChatLog(user_id=user.id, conversation_id=room.id,
                                   question=question, answer=answer))
                    db.commit()
        for message in messages:
            r = client.post("/api/chat", json={"message": message,
                                               "conversation_id": conversation_id})
            assert r.status_code == 200
            conversation_id = r.json()["conversation_id"]
            out.append((r.json()["answer"], json.loads(fake.requests[-1].content)["system"]))
    e.dispose()
    return out


def picked(answer):
    return answered_star(answer)


@pytest.mark.parametrize("seed", range(6))
def test_follow_up_keeps_the_same_star_and_title(monkeypatch, seed):
    (first, _), (second, system) = talk([NEW_GIRLS, "그 사람 어떤 그룹 출신이야?"],
                                        monkeypatch, seed)
    star = picked(first)
    assert star in ("신인걸", "신인걸2")
    assert second.startswith("˗ˋˏ " + star + " ˎˊ˗\n\n")
    assert second.endswith(SOURCE + star)
    assert "\n1. " + star + " (" in system and "\n2. " not in system


@pytest.mark.parametrize("seed", range(4))
def test_keyword_only_follow_up_keeps_the_star(monkeypatch, seed):
    # a new search would prefer 신인걸2, whose chunk has '막내'
    (first, _), (second, system) = talk([NEW_GIRLS, "막내는?"], monkeypatch, seed)
    assert picked(second) == picked(first)
    assert "\n2. " not in system


def test_follow_up_keeps_a_title_with_a_parenthesized_part(monkeypatch):
    before = [("트와이스 멤버 추천해줘", "˗ˋˏ 모모 ˎˊ˗\n\n모모!\n\n" + SOURCE + "모모(TWICE)")]
    [(answer, system)] = talk(["걔 춤 실력은?"], monkeypatch, before=before)
    assert answer == "˗ˋˏ 모모 ˎˊ˗\n\n" + REPLY + "\n\n" + SOURCE + "모모(TWICE)"
    assert "1. 모모(TWICE) (" in system and "춤 실력으로 유명하다" in system


@pytest.mark.parametrize("seed", range(6))
def test_another_person_excludes_the_stars_already_recommended(monkeypatch, seed):
    answers = talk([NEW_GIRLS, "다른 사람 추천해줘", "또 다른 사람 있어?"], monkeypatch, seed)
    first, second = picked(answers[0][0]), picked(answers[1][0])
    assert {first, second} == {"신인걸", "신인걸2"}
    # both are already recommended: no star is made up, so no title and no source
    third, system = answers[2]
    assert picked(third) is None and third == REPLY and not system.endswith("</참고자료>")


def test_another_person_after_a_same_star_follow_up_keeps_the_conditions(monkeypatch):
    answers = talk([NEW_GIRLS, "걔 키 몇이야?", "다른 애로 바꿔줘"], monkeypatch)
    assert picked(answers[0][0]) == picked(answers[1][0])
    assert {picked(answers[0][0]), picked(answers[2][0])} == {"신인걸", "신인걸2"}


def test_question_with_new_conditions_picks_fresh(monkeypatch):
    answers = talk(["안경 쓴 부산 출신 아이돌 추천해줘", "보조개 있는 남자 배우 추천해줘",
                    "아이유는 어때?"], monkeypatch)
    assert [picked(a) for a, _ in answers] == ["부산돌", "부산배우", "아이유"]


def test_unknown_previous_star_falls_back_to_the_search(monkeypatch):
    before = [("안경 쓴 부산 출신 아이돌 추천해줘",
               "˗ˋˏ 없는사람 ˎˊ˗\n\n추천!\n\n" + SOURCE + "없는사람")]
    [(answer, system)] = talk(["그 사람 어때?"], monkeypatch, before=before)
    assert picked(answer) == "부산돌" and "없는사람" not in system


def test_lookup_failure_never_raises(caplog):
    broken = create_engine("sqlite://")  # no tables
    assert find_star(broken, "부산돌", "그 사람 어때?") is None
    assert "star_lookup_failure" in caplog.text
    broken.dispose()


def test_find_star_by_title_alias_and_display_name(engine):  # noqa: F811
    assert find_star(engine, "모모(TWICE)").stars[0]["title"] == "모모(TWICE)"
    assert find_star(engine, "모모").stars[0]["title"] == "모모(TWICE)"
    assert find_star(engine, "임나연").stars[0]["title"] == "나연"
    assert find_star(engine, "없는사람") is None
    assert find_star(engine, "") is None and find_star(engine, None) is None
    found = find_star(engine, "모모", "그 사람 춤 실력 어때?").stars[0]
    assert found["matched"] and any("실력" in s["text"] for s in found["snippets"])
    assert find_star(engine, "모모", "아이유는?", unless_other_named=True) is None


def test_answered_star_reads_the_source_or_title_line():
    assert answered_star("˗ˋˏ 모모 ˎˊ˗\n\n본문\n\n" + SOURCE + "모모(TWICE)") == "모모(TWICE)"
    assert answered_star("˗ˋˏ 모모 ˎˊ˗\n\n본문") == "모모"
    assert answered_star("˗ˋˏ 모모 ˎˊ˗\n\n본문\n\n" + SOURCE + "모모(TWICE), 나연") == "모모"
    assert answered_star("그냥 답") is None and answered_star(None) is None


@pytest.mark.parametrize("message, mode", [
    ("다른 사람 추천해줘", "another"),
    ("한 명 더", "another"),
    ("강혜원 말고", "another"),
    ("강혜원은 말고 다른 애", "another"),
    ("부산돌 말고", "another"),
    ("그 사람 말고 추천해줘", "another"),
    ("걔 말고", "another"),
    ("말고 다른 애 없어?", "another"),
    ("다른 애로 바꿔줘", "another"),
    ("바꿔줘", "another"),
    ("또 추천해줘", "another"),
    ("그 사람 어떤 그룹 출신이야?", "same"),
    ("걔는 키 커?", "same"),
    ("그녀의 데뷔곡은?", "same"),
    ("이 사람 부산 출신이야?", "same"),
    ("그분 얘기 더 해줘", "same"),
    ("더 알려줘", "same_unless_named"),
    ("노래 잘해?", "same_unless_named"),
    ("노래 말고 다른 특기 있어?", "same_unless_named"),
    ("머리 바꿔본 적 있어?", "same_unless_named"),
    ("스타일 바꿔본 적 있어?", "same_unless_named"),
    ("연기 말고 노래도 해?", "same_unless_named"),
    ("안경 쓴 애 있어?", "search"),
    ("그 사람이랑 비슷한 가수 추천해줘", "similar"),
    ("걔랑 비슷한 사람", "similar"),
    ("서울 출신 배우 추천해줘", "search"),
    ("그 중에 보조개 있는 사람", "search"),
    ("싱어송라이터 추천해줘", "search"),
    ("아이유랑 비슷한 가수", "search"),
])
def test_follow_up_mode(message, mode):
    assert follow_up_mode(message, "부산돌", lambda word: word in ("강혜원", "강혜원은")) == mode


def test_name_before_malgo_is_checked_against_the_star_data(engine):  # noqa: F811
    assert follow_up_mode("나연 말고", "부산돌",
                          lambda word: is_star_name(engine, word)) == "another"
    assert follow_up_mode("노래 말고 다른 특기 있어?", "부산돌",
                          lambda word: is_star_name(engine, word)) == "same_unless_named"
    assert is_star_name(engine, "임나연은") and not is_star_name(engine, "노래")


def test_similar_to_the_previous_star_searches_around_that_star(monkeypatch):
    before = [("발라드 가수 추천해줘", "˗ˋˏ 아이유 ˎˊ˗\n\n추천!\n\n" + SOURCE + "아이유")]
    [(answer, system)] = talk(["그 사람이랑 비슷한 가수 추천해줘"], monkeypatch, before=before)
    assert picked(answer) not in (None, "아이유")
    assert "아이유와 성별·활동 분야·데뷔 시기가 비슷한 스타" in system


def test_without_a_previous_star_every_question_is_a_search():
    assert follow_up_mode("그 사람 어때?", None) == "search"
    assert follow_up_mode("다른 사람 추천해줘", None) == "another"


def glasses_star(engine):  # noqa: F811
    """부산돌 with the 안경 chunk past the default snippets."""
    with engine.begin() as conn:
        conn.execute(update(StarChunk).where(StarChunk.profile_id == 4,
                                             StarChunk.chunk_index == 1)
                     .values(content="데뷔 전에는 연습생이었다."))
        conn.execute(StarChunk.__table__.insert(), [
            dict(profile_id=4, chunk_index=2, section="활동", content="노래 실력이 좋다.",
                 source_url="u"),
            dict(profile_id=4, chunk_index=3, section="여담",
                 content="무대 밖에서는 안경을 자주 쓴다.", source_url="u")])
    return engine


FIRST = SimpleNamespace(question="안경 쓴 부산 출신 아이돌 추천해줘",
                        answer="˗ˋˏ 부산돌 ˎˊ˗\n\n안경을 자주 써!\n\n" + SOURCE + "부산돌")


@pytest.mark.parametrize("message, expected", [
    ("그 사람 어떤 그룹 출신이야?", ["직업", "안경", "연습생"]),
    ("걔 노래 실력은 어때?", ["직업", "노래", "안경"]),
])
def test_same_star_follow_up_keeps_the_earlier_keyword_chunk(engine, message,  # noqa: F811
                                                             expected):
    found = chat_service._find_reference(glasses_star(engine), message, [FIRST], "t")
    texts = [s["text"] for s in found.stars[0]["snippets"]]
    assert found.names == ["부산돌"] and len(texts) == len(expected) <= 3
    assert all(word in text for word, text in zip(expected, texts))


def test_earlier_keywords_come_only_from_questions_about_that_star():
    other = SimpleNamespace(question="보조개 있는 남자 배우 추천해줘",
                            answer="˗ˋˏ 부산배우 ˎˊ˗\n\n추천!\n\n" + SOURCE + "부산배우")
    after = SimpleNamespace(question="걔 노래는?", answer=FIRST.answer)
    assert chat_service._earlier_keywords([other, FIRST, after], "부산돌") == ["안경", "노래"]


def test_find_star_without_earlier_keywords_keeps_two_snippets(engine):  # noqa: F811
    found = find_star(glasses_star(engine), "부산돌", "걔 노래 실력은 어때?").stars[0]
    assert [s["section"] for s in found["snippets"]] == ["프로필", "활동"]


def test_system_prompt_does_not_retract_earlier_details():
    assert "사과하거나 잘못 말했다고 정정하지 마" in SYSTEM_PROMPT
    assert "새 질문에 답하는 데 집중해" in SYSTEM_PROMPT
