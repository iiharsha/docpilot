"""The thread routes: who may see a thread, and what comes back.

Patched at `app.database.chats` rather than at the query builder. The guard, the
status codes, and the serialised shape are what this phase owns; PostgREST's
call chain is not, and faking `.table().select().eq()` would test the fake.
"""

import uuid

from app.database import chats

CREATED_AT = "2026-09-22T10:00:00+00:00"
UPDATED_AT = "2026-09-22T10:05:00+00:00"


def thread_row(
    user_id: uuid.UUID, thread_id: uuid.UUID, title: str | None = "Apple FY24 margins"
) -> dict:
    """A thread as PostgREST returns one — uuid columns arrive as strings."""
    return {
        "id": str(thread_id),
        "user_id": str(user_id),
        "title": title,
        "created_at": CREATED_AT,
        "updated_at": UPDATED_AT,
    }


def test_list_threads_returns_camel_case(
    client, current_user, user_client, monkeypatch
):
    captured = {}

    async def fake_list_threads(db_client, user_id):
        captured.update(client=db_client, user_id=user_id)
        return [thread_row(current_user.id, uuid.uuid4())]

    monkeypatch.setattr(chats, "list_threads", fake_list_threads)

    response = client.get("/threads")

    assert response.status_code == 200
    # Reads go through the user client: RLS is a second, independent lock.
    assert captured["client"] == user_client
    assert captured["user_id"] == current_user.id

    thread = response.json()[0]
    assert set(thread) == {"id", "title", "createdAt", "updatedAt"}
    assert thread["createdAt"] == "2026-09-22T10:00:00Z"


def test_create_thread_writes_with_the_service_client(
    client, current_user, service_client, monkeypatch
):
    captured = {}

    async def fake_create_thread(db_client, user_id, title):
        captured.update(client=db_client, user_id=user_id, title=title)
        return thread_row(user_id, uuid.uuid4(), title)

    monkeypatch.setattr(chats, "create_thread", fake_create_thread)

    response = client.post("/threads", json={"title": "Apple FY24 margins"})

    assert response.status_code == 201
    # There is no insert policy to satisfy, and the owner is taken from the
    # verified token rather than from anything the caller sent.
    assert captured["client"] == service_client
    assert captured["user_id"] == current_user.id
    assert response.json()["title"] == "Apple FY24 margins"


def test_create_thread_rejects_an_oversize_title(client):
    response = client.post("/threads", json={"title": "x" * 201})

    assert response.status_code == 422


def test_owner_reads_their_message_history(
    client, current_user, user_client, monkeypatch
):
    thread_id = uuid.uuid4()
    captured = {}

    async def fake_fetch_thread(db_client, requested_id):
        return thread_row(current_user.id, requested_id)

    async def fake_list_messages(db_client, requested_id):
        captured.update(client=db_client, thread_id=requested_id)
        return [
            {
                "id": str(uuid.uuid4()),
                "role": "assistant",
                "content": "Gross margin was 46.2%.",
                "sequence": 2,
                "created_at": CREATED_AT,
            }
        ]

    monkeypatch.setattr(chats, "fetch_thread", fake_fetch_thread)
    monkeypatch.setattr(chats, "list_messages", fake_list_messages)

    response = client.get(f"/threads/{thread_id}/messages")

    assert response.status_code == 200
    # Ownership is already proven, so this client only has to be scoped.
    assert captured["client"] == user_client
    assert captured["thread_id"] == thread_id

    message = response.json()[0]
    assert message["createdAt"] == "2026-09-22T10:00:00Z"
    assert message["citations"] == []


def test_string_user_id_from_postgrest_still_matches_the_owner(
    client, current_user, service_client, monkeypatch
):
    """Regression: `row["user_id"]` is a string and `user.id` is a `UUID`.

    Comparing them directly is unequal every time, which 403s the owner out of
    their own thread — a failure that only shows up against a real database.
    """
    thread_id = uuid.uuid4()
    captured = {}

    async def fake_fetch_thread(db_client, requested_id):
        captured["client"] = db_client
        row = thread_row(current_user.id, requested_id)
        assert isinstance(row["user_id"], str)
        return row

    async def no_messages(db_client, requested_id):
        return []

    monkeypatch.setattr(chats, "fetch_thread", fake_fetch_thread)
    monkeypatch.setattr(chats, "list_messages", no_messages)

    response = client.get(f"/threads/{thread_id}/messages")

    assert response.status_code == 200
    # The lookup has to bypass RLS, or a foreign thread reads as a missing one.
    assert captured["client"] == service_client


def test_another_users_thread_is_forbidden(client, monkeypatch):
    async def fake_fetch_thread(db_client, requested_id):
        return thread_row(uuid.uuid4(), requested_id)

    monkeypatch.setattr(chats, "fetch_thread", fake_fetch_thread)

    response = client.get(f"/threads/{uuid.uuid4()}/messages")

    assert response.status_code == 403


def test_a_thread_that_does_not_exist_is_not_found(client, monkeypatch):
    async def fake_fetch_thread(db_client, requested_id):
        return None

    monkeypatch.setattr(chats, "fetch_thread", fake_fetch_thread)

    response = client.get(f"/threads/{uuid.uuid4()}/messages")

    assert response.status_code == 404


def test_a_request_without_a_token_is_unauthorized(anonymous_client):
    response = anonymous_client.get("/threads")

    assert response.status_code == 401
    # RFC 7235: a 401 has to say how to authenticate.
    assert response.headers["WWW-Authenticate"] == "Bearer"


def test_a_thread_id_that_is_not_a_uuid_is_unprocessable(client):
    response = client.get("/threads/not-a-uuid/messages")

    assert response.status_code == 422
