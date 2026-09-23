"""Fixtures for the fast suite.

Tests drive the real app through `TestClient` with the three Supabase
dependencies replaced, so nothing here opens a socket — overriding
`get_current_user` is also what keeps the `public.users` upsert out of the
suite. What a route then does with a client is patched at the
`app.database.chats` boundary by the tests themselves.
"""

import uuid
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.auth.dependencies import AuthenticatedUser, get_current_user, get_user_client
from app.dependencies import get_service_client
from app.main import app

CURRENT_USER = AuthenticatedUser(
    id=uuid.UUID("11111111-1111-4111-8111-111111111111"),
    email="analyst@bluewood.test",
)

# Stand-ins for the two Supabase clients. Every call that would use one is
# patched out, so their only job is to be tellable apart: which client a route
# reaches for is a security decision, and the tests check it.
USER_CLIENT = "user-client"
SERVICE_CLIENT = "service-client"


@pytest.fixture
def current_user() -> AuthenticatedUser:
    return CURRENT_USER


@pytest.fixture
def user_client() -> str:
    return USER_CLIENT


@pytest.fixture
def service_client() -> str:
    return SERVICE_CLIENT


@pytest.fixture
def client() -> Iterator[TestClient]:
    """A caller whose token has already been verified."""
    app.dependency_overrides[get_current_user] = lambda: CURRENT_USER
    app.dependency_overrides[get_user_client] = lambda: USER_CLIENT
    app.dependency_overrides[get_service_client] = lambda: SERVICE_CLIENT
    try:
        # Not used as a context manager: the lifespan builds the real
        # service-role client, which every test overrides anyway.
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def anonymous_client() -> TestClient:
    """No overrides, so the real auth dependencies answer the request."""
    return TestClient(app)
