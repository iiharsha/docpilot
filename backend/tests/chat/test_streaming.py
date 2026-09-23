"""The wire format `ai@7.0.107` parses.

Every assertion here is a copy of a `UIMessageChunk` variant from the SDK's own
type definitions. A part renamed by an SDK upgrade — `delta` was `textDelta` in
an earlier release — breaks here rather than as a chat that never renders.
"""

import json

from app.chat import streaming


def parse(frame: str) -> dict:
    """The JSON inside one server-sent event."""
    assert frame.startswith("data: ")
    assert frame.endswith("\n\n")
    return json.loads(frame.removeprefix("data: "))


def test_start_names_the_message():
    assert streaming.start("m1") == {"type": "start", "messageId": "m1"}


def test_text_parts_carry_the_block_id():
    assert streaming.text_start("m1") == {"type": "text-start", "id": "m1"}
    assert streaming.text_end("m1") == {"type": "text-end", "id": "m1"}


def test_text_delta_uses_the_delta_key():
    assert streaming.text_delta("m1", "Gross ") == {
        "type": "text-delta",
        "id": "m1",
        "delta": "Gross ",
    }


def test_finish_closes_the_message():
    assert streaming.finish() == {"type": "finish"}


def test_error_uses_the_error_text_key():
    assert streaming.error("nope") == {"type": "error", "errorText": "nope"}


def test_sse_frames_a_part_as_one_event():
    frame = streaming.sse(streaming.text_delta("m1", "46.2%"))

    assert frame == 'data: {"type":"text-delta","id":"m1","delta":"46.2%"}\n\n'
    assert parse(frame)["delta"] == "46.2%"


def test_sse_keeps_multibyte_text_intact():
    """A filing's en dashes and £ signs must survive the JSON encoder."""
    frame = streaming.sse(streaming.text_delta("m1", "£1.2bn – up"))

    assert "£1.2bn – up" in frame
    assert parse(frame)["delta"] == "£1.2bn – up"


def test_a_newline_in_the_answer_does_not_split_the_event():
    """A raw newline in `data:` would end the frame early and lose the rest."""
    frame = streaming.sse(streaming.text_delta("m1", "one\ntwo"))

    assert frame.count("\n\n") == 1
    assert parse(frame)["delta"] == "one\ntwo"


def test_headers_declare_the_protocol_the_client_expects():
    assert streaming.STREAM_HEADERS["x-vercel-ai-ui-message-stream"] == "v1"
    # A proxy that buffers the body turns a stream into one late blob.
    assert streaming.STREAM_HEADERS["x-accel-buffering"] == "no"
    assert streaming.MEDIA_TYPE == "text/event-stream"


def test_done_terminates_the_stream():
    assert streaming.DONE == "data: [DONE]\n\n"
