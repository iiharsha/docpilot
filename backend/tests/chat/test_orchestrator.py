"""Thread titles derived from a first question.

The sidebar has nothing else to show — a thread is created untitled, before
anyone has typed anything — so this is what makes the thread list readable.
"""

from app.chat.orchestrator import TITLE_MAX_LENGTH, thread_title


def test_a_short_question_is_the_title():
    assert thread_title("Apple FY24 gross margins") == "Apple FY24 gross margins"


def test_wrapped_whitespace_is_collapsed():
    """A textarea keeps the newlines the analyst typed; a sidebar row cannot."""
    assert thread_title("Apple FY24\n  gross   margins\n") == "Apple FY24 gross margins"


def test_a_long_question_is_truncated_to_the_column_bound():
    """Bounded like `ThreadCreate.title`, so a pasted filing cannot be a title."""
    title = thread_title("Apple " * 100)

    assert len(title) <= TITLE_MAX_LENGTH
    assert title.endswith("…")


def test_truncation_does_not_leave_a_trailing_space():
    title = thread_title("ab " * 200)

    assert not title.removesuffix("…").endswith(" ")
