"""Source line handling: history stripping, model-written lines, and listed names."""
from types import SimpleNamespace

from app.services.ai_client import build_messages

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
