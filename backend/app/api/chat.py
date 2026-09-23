"""The chat streaming route.

Authentication, the thread lookup and the ownership check all resolve before the
first byte, so they stay real status codes. Everything after that belongs to
`chat.orchestrator`, which has only the stream to report failures through.
"""

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse

from app.api.threads import authorize_thread
from app.auth.dependencies import CurrentUser
from app.chat import streaming
from app.chat.messages import StreamRequest, question_from
from app.chat.orchestrator import run_turn
from app.dependencies import ServiceClient

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("/stream")
async def stream_chat(
    payload: StreamRequest, user: CurrentUser, service_client: ServiceClient
) -> StreamingResponse:
    """Answer the caller's latest message in their thread, streaming as it goes."""
    # `threadId` arrives in the body rather than the path, which is why the
    # guard takes ids: the same 404-vs-403 rule as the thread routes.
    thread = await authorize_thread(service_client, payload.thread_id, user.id)

    try:
        question = question_from(payload.messages)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc

    return StreamingResponse(
        run_turn(service_client, thread, question),
        media_type=streaming.MEDIA_TYPE,
        headers=streaming.STREAM_HEADERS,
    )
