"""FastAPI entrypoint."""

import logging
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.auth import router as auth_router
from app.api.chat import router as chat_router
from app.api.threads import router as threads_router
from app.config import settings
from app.database.supabase import create_service_client
from app.errors import register_exception_handlers


def configure_logging() -> None:
    """Readable logs on a terminal, JSON when piped to a log collector."""
    if sys.stderr.isatty():
        renderers = [structlog.dev.ConsoleRenderer()]
    else:
        renderers = [
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ]

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.dev.set_exc_info,
            *renderers,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        cache_logger_on_first_use=True,
    )


configure_logging()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # One privileged client per process. Construction is local — it opens no
    # connection — so startup does not depend on Supabase being reachable.
    app.state.supabase_service = await create_service_client()
    yield


app = FastAPI(title="Docpilot API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Every route reaches Supabase, so the failure modes of that call are handled
# once here rather than in each of them.
register_exception_handlers(app)

app.include_router(auth_router)
app.include_router(chat_router)
app.include_router(threads_router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
