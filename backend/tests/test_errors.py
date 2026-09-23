"""The 502s every route inherits.

Driven through a real route rather than by calling the handlers directly: what
is worth checking is that a bare `APIError` or httpx failure raised inside a
route is caught at all, which depends on the handlers being registered for
exception types Starlette has no opinion about.
"""

import httpx
from postgrest.exceptions import APIError

from app.database import chats


def test_a_rejected_query_is_a_bad_gateway(client, monkeypatch):
    async def fail(db_client, user_id):
        raise APIError(
            {"message": "column does not exist", "code": "42703", "hint": None}
        )

    monkeypatch.setattr(chats, "list_threads", fail)

    response = client.get("/threads")

    assert response.status_code == 502
    assert response.json() == {"detail": "Database request failed"}


def test_an_unreachable_database_is_a_bad_gateway(client, monkeypatch):
    async def fail(db_client, user_id):
        # postgrest wraps error responses, but a transport failure comes
        # through raw, so it needs a handler of its own.
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(chats, "list_threads", fail)

    response = client.get("/threads")

    assert response.status_code == 502
    assert response.json() == {"detail": "Database unavailable"}
