from __future__ import annotations

from brainbot.telegram.topics import TopicName
from brainbot.telegram.webhook import (
    is_allowed_user,
    parse_update,
    verify_secret,
)


def _message_update(*, text: str, thread_id: int | None, user_id: int = 42) -> dict:
    return {
        "update_id": 1,
        "message": {
            "message_id": 10,
            "from": {"id": user_id, "is_bot": False},
            "chat": {"id": -100123, "type": "supergroup"},
            "text": text,
            "message_thread_id": thread_id,
        },
    }


def test_parses_message_into_topic() -> None:
    msg = parse_update(_message_update(text="hello", thread_id=300))
    assert msg is not None
    assert msg.text == "hello"
    assert msg.topic is TopicName.TODOS
    assert msg.user_id == 42


def test_returns_none_for_unsupported_update() -> None:
    assert parse_update({"update_id": 1}) is None


def test_callback_update_parses_with_is_callback() -> None:
    cb = {
        "update_id": 2,
        "callback_query": {
            "id": "cb-1",
            "from": {"id": 42},
            "data": "delete:yes",
            "message": {
                "message_id": 11,
                "chat": {"id": -100123},
                "message_thread_id": 100,
            },
        },
    }
    msg = parse_update(cb)
    assert msg is not None
    assert msg.is_callback is True
    assert msg.callback_data == "delete:yes"
    assert msg.topic is TopicName.EMAILS


def test_verify_secret_matches() -> None:
    assert verify_secret("test-secret") is True
    assert verify_secret("wrong") is False
    assert verify_secret(None) is False


def test_is_allowed_user() -> None:
    assert is_allowed_user(42) is True
    assert is_allowed_user(99999) is False
