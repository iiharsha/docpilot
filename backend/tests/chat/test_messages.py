"""Reading a question out of what the browser posted.

The client sends its whole visible conversation; only the last user message is
the question. The rest is history the backend already has, and must not be
taken from a request body.
"""

import uuid

import pytest
from pydantic import ValidationError

from app.chat.messages import StreamRequest, UIMessage, question_from


def user_says(text: str) -> UIMessage:
    return UIMessage.model_validate(
        {"role": "user", "parts": [{"type": "text", "text": text}]}
    )


def assistant_says(text: str) -> UIMessage:
    return UIMessage.model_validate(
        {"role": "assistant", "parts": [{"type": "text", "text": text}]}
    )


def test_the_last_user_message_is_the_question():
    question = question_from(
        [
            user_says("What were Apple's FY24 gross margins?"),
            assistant_says("46.2%."),
            user_says("And FY23?"),
        ]
    )

    assert question == "And FY23?"


def test_parts_of_one_message_are_joined():
    message = UIMessage.model_validate(
        {
            "role": "user",
            "parts": [
                {"type": "text", "text": "Compare Apple "},
                {"type": "text", "text": "and Microsoft."},
            ],
        }
    )

    assert question_from([message]) == "Compare Apple and Microsoft."


def test_non_text_parts_are_ignored():
    """The SDK's part union grows between releases; unknown kinds carry no text."""
    message = UIMessage.model_validate(
        {
            "role": "user",
            "parts": [
                {"type": "step-start"},
                {"type": "text", "text": "Revenue?"},
            ],
        }
    )

    assert question_from([message]) == "Revenue?"


def test_surrounding_whitespace_is_dropped():
    assert question_from([user_says("  Revenue?\n")]) == "Revenue?"


def test_an_assistant_turn_is_not_a_question():
    """Answering one would mean generating a reply to ourselves."""
    with pytest.raises(ValueError, match="assistant"):
        question_from([user_says("Revenue?"), assistant_says("$391bn.")])


def test_an_empty_message_is_rejected():
    with pytest.raises(ValueError, match="no text"):
        question_from([user_says("   ")])


def test_a_message_with_no_text_part_is_rejected():
    message = UIMessage.model_validate({"role": "user", "parts": [{"type": "file"}]})

    with pytest.raises(ValueError, match="no text"):
        question_from([message])


def test_the_request_validates_camel_case():
    """The AI SDK builds this body itself and sends `threadId`."""
    thread_id = uuid.uuid4()

    request = StreamRequest.model_validate(
        {
            "threadId": str(thread_id),
            "messages": [{"role": "user", "parts": [{"type": "text", "text": "Hi"}]}],
        }
    )

    assert request.thread_id == thread_id


def test_the_request_ignores_the_sdk_session_fields():
    """`id`, `trigger` and `messageId` describe a session the backend does not track."""
    request = StreamRequest.model_validate(
        {
            "threadId": str(uuid.uuid4()),
            "messages": [{"role": "user", "parts": [{"type": "text", "text": "Hi"}]}],
            "id": "chat-1",
            "trigger": "submit-message",
            "messageId": "m1",
        }
    )

    assert request.messages[0].parts[0].text == "Hi"


def test_a_request_with_no_messages_is_rejected():
    with pytest.raises(ValidationError):
        StreamRequest.model_validate({"threadId": str(uuid.uuid4()), "messages": []})
