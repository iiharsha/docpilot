"""Shared FastAPI dependencies that are not specific to auth."""

from typing import Annotated

from fastapi import Depends, Request
from supabase import AsyncClient


async def get_service_client(request: Request) -> AsyncClient:
    """The process-wide privileged client, created in `main.lifespan`.

    Bypasses RLS, so every query through it must scope itself to the
    authenticated user explicitly.
    """
    client: AsyncClient = request.app.state.supabase_service
    return client


ServiceClient = Annotated[AsyncClient, Depends(get_service_client)]
