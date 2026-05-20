from __future__ import annotations

from brainbot.telegram.topics import TopicName, thread_id_for_topic, topic_for_thread_id


def test_known_thread_resolves_to_topic() -> None:
    assert topic_for_thread_id(100) is TopicName.EMAILS
    assert topic_for_thread_id(300) is TopicName.TODOS
    assert topic_for_thread_id(400) is TopicName.SECOND_BRAIN


def test_unknown_thread_falls_back_to_general() -> None:
    assert topic_for_thread_id(999_999) is TopicName.GENERAL
    assert topic_for_thread_id(None) is TopicName.GENERAL


def test_round_trip_thread_id() -> None:
    for topic in (TopicName.EMAILS, TopicName.CALENDAR, TopicName.TODOS):
        tid = thread_id_for_topic(topic)
        assert tid is not None
        assert topic_for_thread_id(tid) is topic
