"""Source line handling: history stripping, model-written lines, and listed names."""
from types import SimpleNamespace

import httpx
from test_chat_api import ACCOUNT, FakeAI
from test_star_search import chat_client, chat_engine

from app.services.ai_client import build_messages
from app.services.star_search import remove_source_lines

CREDIT = "출처: 나무위키(CC BY-NC-SA 2.0 KR) - 조유리, 산들"


def pair(question, answer):
    return SimpleNamespace(question=question, answer=answer)


def test_history_answers_lose_the_trailing_source_line():
    history = [pair("q1", "조유리를 추천해요.\n\n" + CREDIT), pair("q2", "그냥 답")]
    messages = build_messages(history, "q3")
    assert messages[1] == {"role": "assistant", "content": "조유리를 추천해요."}
    assert messages[3]["content"] == "그냥 답"
    assert messages[4] == {"role": "user", "content": "q3"}


def test_history_keeps_source_text_that_is_not_the_last_line():
    answer = CREDIT + "\n라고 쓰여 있어요."
    assert build_messages([pair("q", answer)], "n")[1]["content"] == answer


def test_remove_source_lines_drops_model_written_lines_and_trailing_blanks():
    text = "조유리를 추천해요.\n" + CREDIT + "\n\n"
    assert remove_source_lines(text) == "조유리를 추천해요."
    assert remove_source_lines("앞\n출처: 어딘가\n뒤") == "앞\n뒤"
    assert remove_source_lines("출처가 궁금하면 말해요.") == "출처가 궁금하면 말해요."


def test_chat_shows_exactly_one_source_line_when_model_copies_it():
    copied = "부산돌을 추천해요.\n\n출처: 나무위키(CC BY-NC-SA 2.0 KR) - 부산돌"
    fake = FakeAI()
    fake.handler = lambda request: httpx.Response(
        200, json={"content": [{"type": "text", "text": copied}]})
    e = chat_engine()
    client, _ = chat_client(e, fake)
    with client:
        client.post("/api/auth/register", json=ACCOUNT)
        client.post("/api/auth/login", json=ACCOUNT)
        r = client.post("/api/chat", json={"message": "안경 쓴 부산 출신 아이돌 추천해줘"})
    answer = r.json()["answer"]
    assert answer.count("출처:") == 1
    assert answer == "부산돌을 추천해요.\n\n출처: 나무위키(CC BY-NC-SA 2.0 KR) - 부산돌"
    e.dispose()
