"""End-to-end webhook test against the FastAPI app.

Mocks out the agent router so we don't touch Gemini or the network.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client() -> TestClient:
    # Import inside the fixture so conftest env vars are applied first.
    from brainbot.main import app

    # Patch the scheduler hooks: they'd otherwise try to talk to postgres.
    with (
        patch("brainbot.scheduler.jobs.start_scheduler", new=AsyncMock()),
        patch("brainbot.scheduler.jobs.stop_scheduler", new=AsyncMock()),
    ):
        with TestClient(app) as c:
            yield c


def _msg_body(text: str, thread_id: int = 300, user_id: int = 42) -> dict:
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


def test_healthz(client: TestClient) -> None:
    assert client.get("/healthz").json() == {"status": "ok"}


def test_webhook_rejects_missing_secret(client: TestClient) -> None:
    r = client.post("/telegram/webhook", json=_msg_body("hi"))
    assert r.status_code == 403


def test_webhook_rejects_bad_secret(client: TestClient) -> None:
    r = client.post(
        "/telegram/webhook",
        json=_msg_body("hi"),
        headers={"X-Telegram-Bot-Api-Secret-Token": "wrong"},
    )
    assert r.status_code == 403


def test_webhook_ignores_unauthorised_user(client: TestClient) -> None:
    with patch("brainbot.agents.router.route", new=AsyncMock()) as route:
        r = client.post(
            "/telegram/webhook",
            json=_msg_body("hi", user_id=99999),
            headers={"X-Telegram-Bot-Api-Secret-Token": "test-secret"},
        )
        assert r.status_code == 200
        assert r.json()["ignored"] == "unauthorised"
        route.assert_not_awaited()


def test_webhook_dispatches_authorised_user(client: TestClient) -> None:
    with patch("brainbot.agents.router.route", new=AsyncMock()) as route:
        r = client.post(
            "/telegram/webhook",
            json=_msg_body("add: buy milk"),
            headers={"X-Telegram-Bot-Api-Secret-Token": "test-secret"},
        )
        assert r.status_code == 200
        assert r.json() == {"ok": True}
        route.assert_awaited_once()
