"""Application-wide exception handlers.

Every route in this service talks to PostgREST, so a failed database request is
not an exceptional case for any one of them — it is the same 502 everywhere.
Handling it here keeps routes free of `try/except` blocks whose only job is to
relabel an exception.

Both handlers are needed: postgrest wraps error *responses* in `APIError`, but a
connection failure propagates as a raw httpx error, which would otherwise be a
500 for something that is not the caller's fault.
"""

import httpx
import structlog
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from postgrest.exceptions import APIError

log = structlog.get_logger(__name__)


def _bad_gateway(detail: str) -> JSONResponse:
    return JSONResponse({"detail": detail}, status.HTTP_502_BAD_GATEWAY)


async def handle_database_error(request: Request, exc: APIError) -> JSONResponse:
    """Postgres or PostgREST rejected the query."""
    # Phase 3 will need to split this: a concurrent double-send violates
    # `uq_chat_messages_thread_sequence`, and that `23505` is a 409, not a 502.
    log.warning(
        "database_request_failed",
        path=request.url.path,
        code=exc.code,
        message=exc.message,
    )
    return _bad_gateway("Database request failed")


async def handle_transport_error(
    request: Request, exc: httpx.HTTPError
) -> JSONResponse:
    """Supabase was unreachable, or the request timed out."""
    log.warning("database_unreachable", path=request.url.path, error=str(exc))
    return _bad_gateway("Database unavailable")


def register_exception_handlers(app: FastAPI) -> None:
    # These run only while a response is still being *built*. Once
    # `/chat/stream` has sent its first byte the status line is gone, so that
    # route has to report failures as typed error events in the stream itself.
    app.add_exception_handler(APIError, handle_database_error)
    app.add_exception_handler(httpx.HTTPError, handle_transport_error)
