"""Shared FastAPI dependencies that are not specific to auth."""

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine
from supabase import AsyncClient


async def get_service_client(request: Request) -> AsyncClient:
    """The process-wide privileged client, created in `main.lifespan`.

    Bypasses RLS, so every query through it must scope itself to the
    authenticated user explicitly.
    """
    client: AsyncClient = request.app.state.supabase_service
    return client


ServiceClient = Annotated[AsyncClient, Depends(get_service_client)]


async def get_database_connection(request: Request) -> AsyncIterator[AsyncConnection]:
    """A pooled connection for this request, from the engine `main.lifespan` built.

    It goes back to the pool once the response has been sent — for a streamed
    response, after its last byte, so a stream can keep reading through it.
    """
    engine: AsyncEngine = request.app.state.database_engine
    async with engine.connect() as connection:
        yield connection


DatabaseConnection = Annotated[AsyncConnection, Depends(get_database_connection)]
