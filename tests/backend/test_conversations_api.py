"""Conversations: POST /api/chat with conversation_id and /api/me/conversations*."""
import json
import random
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from sqlalchemy import func, select
from test_chat_api import ACCOUNT, FakeAI
from test_star_search import chat_client, chat_engine

from app.models import ChatLog, Conversation, User
from app.services import chat as chat_service
from app.services.star_search import answered_star

OTHER = {"email": "conv-other@example.com", "password": "conv-other-password-123"}
NOT_FOUND = {"error": "CONVERSATION_NOT_FOUND", "message": "대화방을 찾을 수 없습니다."}
REPLY = "응 알려줄게"
NEW_GIRLS = "2020년에 데뷔한 걸그룹 멤버 중에 키 큰 사람"
BASE_TIME = datetime(2026, 10, 1, tzinfo=timezone.utc)


@pytest.fixture
def api(monkeypatch):
    monkeypatch.setattr(chat_service, "rng", random.Random(1))
    fake = FakeAI()
    fake.handler = lambda request: httpx.Response(
        200, json={"content": [{"type": "text", "text": REPLY}]})
    engine = chat_engine()
    client, factory = chat_client(engine, fake)
    with client:
        client.post("/api/auth/register", json=OTHER)
        client.post("/api/auth/register", json=ACCOUNT)
        client.post("/api/auth/login", json=ACCOUNT)
        yield client, factory, fake
    engine.dispose()


def send(client, message, conversation_id=None):
    body = {"message": message}
    if conversation_id is not None:
        body["conversation_id"] = conversation_id
    r = client.post("/api/chat", json=body)
    assert r.status_code == 200, r.text
    return r.json()


def add_room(factory, email, title="남의 방", chats=1):
    with factory() as db:
        uid = db.scalar(select(User.id).where(User.email == email))
        room = Conversation(user_id=uid, title=title)
        db.add(room)
        db.flush()
        for i in range(chats):
            db.add(ChatLog(user_id=uid, conversation_id=room.id, question=f"q{i}",
                           answer=f"a{i}"))
        db.commit()
        return room.id


def count(factory, model):
    with factory() as db:
        return db.scalar(select(func.count()).select_from(model))


def test_missing_id_starts_a_new_conversation_titled_by_the_question(api):
    client, factory, _ = api
    long_question = "가" * 45
    first = send(client, "  밝은 아이돌 추천해줘  ")
    second = send(client, long_question, None)
    assert first["conversation_id"] and second["conversation_id"]
    assert first["conversation_id"] != second["conversation_id"]
    with factory() as db:
        titles = {room.id: room.title for room in db.scalars(select(Conversation))}
    assert titles[first["conversation_id"]] == "밝은 아이돌 추천해줘"
    assert titles[second["conversation_id"]] == "가" * 40 + "…"
    # an explicit null works like a missing field
    r = client.post("/api/chat", json={"message": "안녕", "conversation_id": None})
    assert r.json()["conversation_id"] not in titles


def test_continuing_a_conversation_uses_its_context_and_bumps_updated_at(api):
    client, factory, fake = api
    first = send(client, "첫 질문")
    room = first["conversation_id"]
    with factory() as db:
        db.get(Conversation, room).updated_at = BASE_TIME
        db.commit()
    second = send(client, "두 번째 질문", room)
    assert second["conversation_id"] == room
    messages = json.loads(fake.requests[-1].content)["messages"]
    assert [m["content"] for m in messages] == ["첫 질문", REPLY, "두 번째 질문"]
    with factory() as db:
        updated = db.get(Conversation, room).updated_at
        assert updated.replace(tzinfo=timezone.utc) > BASE_TIME
        assert db.scalar(select(func.count()).select_from(Conversation)) == 1


def test_context_and_follow_up_star_stay_in_their_conversation(api):
    client, _, fake = api
    first = send(client, NEW_GIRLS)
    star = answered_star(first["answer"])
    assert star in ("신인걸", "신인걸2")
    # the same follow-up in a new conversation must not see the star of the first one
    other = send(client, "그 사람 어떤 그룹 출신이야?")
    assert other["conversation_id"] != first["conversation_id"]
    body = json.loads(fake.requests[-1].content)
    assert body["messages"] == [{"role": "user", "content": "그 사람 어떤 그룹 출신이야?"}]
    assert not other["answer"].startswith("˗ˋˏ " + star)
    # back in the first conversation the follow-up keeps that star
    again = send(client, "그 사람 어떤 그룹 출신이야?", first["conversation_id"])
    assert answered_star(again["answer"]) == star


def test_other_users_or_missing_conversation_is_404_without_ai_call(api):
    client, factory, fake = api
    theirs = add_room(factory, OTHER["email"])
    for conversation_id in (theirs, 9999):
        r = client.post("/api/chat", json={"message": "안녕", "conversation_id": conversation_id})
        assert r.status_code == 404 and r.json() == NOT_FOUND
        assert client.get(f"/api/me/conversations/{conversation_id}/chats").json() == NOT_FOUND
        r = client.delete(f"/api/me/conversations/{conversation_id}")
        assert r.status_code == 404 and r.json() == NOT_FOUND
    assert fake.requests == []
    assert count(factory, ChatLog) == 1 and count(factory, Conversation) == 1


@pytest.mark.parametrize("value", ["abc", 1.5, [1]])
def test_invalid_conversation_id_is_422(api, value):
    client, _, fake = api
    r = client.post("/api/chat", json={"message": "안녕", "conversation_id": value})
    assert r.status_code == 422
    assert r.json()["fields"] == [["body", "conversation_id"]]
    assert fake.requests == []


def test_list_is_newest_updated_first_with_counts_and_own_only(api):
    client, factory, _ = api
    add_room(factory, OTHER["email"])
    a = send(client, "방 A")["conversation_id"]
    b = send(client, "방 B")["conversation_id"]
    send(client, "방 A 두 번째", a)
    with factory() as db:
        db.get(Conversation, a).updated_at = BASE_TIME + timedelta(days=2)
        db.get(Conversation, b).updated_at = BASE_TIME + timedelta(days=1)
        db.commit()
    items = client.get("/api/me/conversations").json()["items"]
    assert [(i["id"], i["title"], i["chat_count"]) for i in items] == [(a, "방 A", 2),
                                                                      (b, "방 B", 1)]
    assert set(items[0]) == {"id", "title", "created_at", "updated_at", "chat_count"}
    assert [i["id"] for i in client.get("/api/me/conversations",
                                         params={"limit": 1}).json()["items"]] == [a]
    for limit in ("0", "101", "x"):
        r = client.get("/api/me/conversations", params={"limit": limit})
        assert r.status_code == 422 and r.json()["fields"] == [["query", "limit"]]


def test_chats_of_a_conversation_oldest_first(api):
    client, _, _ = api
    room = send(client, "하나")["conversation_id"]
    send(client, "다른 방")
    send(client, "둘", room)
    data = client.get(f"/api/me/conversations/{room}/chats").json()
    assert data["conversation"] == {"id": room, "title": "하나"}
    assert [i["question"] for i in data["items"]] == ["하나", "둘"]
    assert set(data["items"][0]) == {"id", "question", "answer", "created_at"}


def test_delete_conversation_removes_its_chats_only(api):
    client, factory, _ = api
    theirs = add_room(factory, OTHER["email"])
    room = send(client, "지울 방")["conversation_id"]
    send(client, "지울 방 둘", room)
    keep = send(client, "남길 방")["conversation_id"]
    r = client.delete(f"/api/me/conversations/{room}")
    assert r.status_code == 204 and r.content == b""
    with factory() as db:
        assert sorted(db.scalars(select(Conversation.id))) == sorted([theirs, keep])
        assert {log.conversation_id for log in db.scalars(select(ChatLog))} == {theirs, keep}
    assert client.delete(f"/api/me/conversations/{room}").status_code == 404


def test_deleting_the_last_chat_removes_the_empty_conversation(api):
    client, factory, _ = api
    data = send(client, "하나뿐인 질문")
    room = data["conversation_id"]
    two = send(client, "두 질문 방")
    send(client, "두 질문 방 둘", two["conversation_id"])
    assert client.delete(f"/api/me/chats/{two['id']}").status_code == 204
    assert client.delete(f"/api/me/chats/{data['id']}").status_code == 204
    with factory() as db:
        assert db.get(Conversation, room) is None
        assert db.get(Conversation, two["conversation_id"]) is not None


def test_login_and_origin_are_checked(api):
    client, factory, _ = api
    room = send(client, "질문")["conversation_id"]
    r = client.delete(f"/api/me/conversations/{room}",
                      headers={"Origin": "https://evil.example"})
    assert r.status_code == 403
    client.post("/api/auth/logout")
    for r in (client.get("/api/me/conversations"),
              client.get(f"/api/me/conversations/{room}/chats"),
              client.delete(f"/api/me/conversations/{room}")):
        assert r.status_code == 401
    assert count(factory, Conversation) == 1


def test_openapi_declares_conversation_errors(api):
    client, _, _ = api
    paths = client.get("/openapi.json").json()["paths"]
    assert {int(c) for c in paths["/api/me/conversations"]["get"]["responses"]} == {
        200, 401, 422, 503}
    chats = paths["/api/me/conversations/{conversation_id}/chats"]["get"]["responses"]
    assert {int(c) for c in chats} == {200, 401, 404, 422, 503}
    delete = paths["/api/me/conversations/{conversation_id}"]["delete"]["responses"]
    assert {int(c) for c in delete} == {204, 401, 403, 404, 422, 503}
    example = delete["404"]["content"]["application/json"]["examples"]
    assert example["conversation_not_found"]["value"] == NOT_FOUND
    chat_404 = paths["/api/chat"]["post"]["responses"]["404"]["content"]["application/json"]
    assert chat_404["examples"]["conversation_not_found"]["value"] == NOT_FOUND
    r = client.delete("/api/me/conversations/abc")
    assert r.json() == delete["422"]["content"]["application/json"]["examples"][
        "conversation_id"]["value"]
