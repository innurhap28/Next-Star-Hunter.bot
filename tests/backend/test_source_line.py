"""Source line handling: history stripping, model-written lines, and listed names."""
from types import SimpleNamespace

import httpx
from test_chat_api import ACCOUNT, FakeAI
from test_star_search import chat_client, chat_engine

from app.services.ai_client import build_messages
from app.services.star_search import StarSearchResult, remove_source_lines, source_line

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


def hit(title, aliases=()):
    return {"title": title, "aliases": list(aliases), "snippets": []}


def test_source_line_lists_only_named_stars_in_hit_order():
    result = StarSearchResult(stars=[hit("조유리"), hit("산들(가수)"), hit("아이유", ["이지은"]),
                                     hit("모모(TWICE)")])
    line = source_line(result, "산들과 이지은을 추천해요. 산들은 목소리가 좋아요.")
    assert line == "출처: 나무위키(CC BY-NC-SA 2.0 KR) - 산들(가수), 아이유"


def test_source_line_names_each_star_once_even_with_duplicate_hits():
    result = StarSearchResult(stars=[hit("산들(가수)"), hit("산들(가수)")])
    assert source_line(result, "산들 추천").count("산들(가수)") == 1


def test_source_line_falls_back_to_all_hits_when_no_name_is_in_the_answer():
    result = StarSearchResult(stars=[hit("조유리"), hit("산들(가수)")])
    assert source_line(result, "잘 모르겠어요.").endswith("- 조유리, 산들(가수)")
    assert source_line(result).endswith("- 조유리, 산들(가수)")
    assert source_line(StarSearchResult(), "조유리") == ""


def test_chat_source_line_lists_only_stars_the_answer_names():
    fake = FakeAI()
    fake.handler = lambda request: httpx.Response(
        200, json={"content": [{"type": "text", "text": "부산돌이 잘 맞아요."}]})
    e = chat_engine()
    client, _ = chat_client(e, fake)
    with client:
        client.post("/api/auth/register", json=ACCOUNT)
        client.post("/api/auth/login", json=ACCOUNT)
        r = client.post("/api/chat", json={"message": "부산 출신 추천해줘"})
    answer = r.json()["answer"]
    assert answer.endswith("\n\n출처: 나무위키(CC BY-NC-SA 2.0 KR) - 부산돌")
    assert "부산배우" not in answer
    e.dispose()
