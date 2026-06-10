"""Tests for Slack/Teams webhook notifications."""
from unittest.mock import AsyncMock, patch

import pytest

from app.notifications.webhook import notify_high_score, notify_sla_alert, notify_stage_change


@pytest.mark.asyncio
async def test_notify_no_webhook_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.notifications import webhook as wh_module
    monkeypatch.setattr(wh_module.settings, "slack_webhook_url", "")
    monkeypatch.setattr(wh_module.settings, "teams_webhook_url", "")
    with patch("app.notifications.webhook._post", new_callable=AsyncMock) as mock_post:
        await notify_stage_change("Jane Doe", "Backend Engineer", "hired")
        mock_post.assert_not_called()


@pytest.mark.asyncio
async def test_stage_change_final_fires(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.notifications import webhook as wh_module
    monkeypatch.setattr(wh_module.settings, "slack_webhook_url", "https://hooks.slack.com/test")
    monkeypatch.setattr(wh_module.settings, "teams_webhook_url", "")
    with patch("app.notifications.webhook._post", new_callable=AsyncMock) as mock_post:
        await notify_stage_change("Jane Doe", "Backend Engineer", "hired")
        mock_post.assert_called_once()
        url, payload = mock_post.call_args[0]
        assert "slack.com" in url
        assert "Jane Doe" in payload["text"]
        assert "hired" in payload["text"]


@pytest.mark.asyncio
async def test_stage_change_intermediate_skipped(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.notifications import webhook as wh_module
    monkeypatch.setattr(wh_module.settings, "slack_webhook_url", "https://hooks.slack.com/test")
    monkeypatch.setattr(wh_module.settings, "teams_webhook_url", "")
    with patch("app.notifications.webhook._post", new_callable=AsyncMock) as mock_post:
        await notify_stage_change("Jane Doe", "Backend Engineer", "interview")
        mock_post.assert_not_called()


@pytest.mark.asyncio
async def test_notify_sla_alert(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.notifications import webhook as wh_module
    monkeypatch.setattr(wh_module.settings, "slack_webhook_url", "https://hooks.slack.com/test")
    monkeypatch.setattr(wh_module.settings, "teams_webhook_url", "")
    with patch("app.notifications.webhook._post", new_callable=AsyncMock) as mock_post:
        await notify_sla_alert("Jane Doe", "Backend Engineer", "screening", 8, 7)
        mock_post.assert_called_once()
        _, payload = mock_post.call_args[0]
        assert "SLA breach" in payload["text"]
        assert "8d" in payload["text"]


@pytest.mark.asyncio
async def test_notify_high_score(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.notifications import webhook as wh_module
    monkeypatch.setattr(wh_module.settings, "slack_webhook_url", "https://hooks.slack.com/test")
    monkeypatch.setattr(wh_module.settings, "teams_webhook_url", "")
    with patch("app.notifications.webhook._post", new_callable=AsyncMock) as mock_post:
        await notify_high_score("Jane Doe", "Backend Engineer", 88)
        mock_post.assert_called_once()
        _, payload = mock_post.call_args[0]
        assert "88/100" in payload["text"]
        assert "High-score" in payload["text"]


@pytest.mark.asyncio
async def test_post_swallows_httpx_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    """_post logs and swallows errors so the main request is unaffected."""
    import httpx

    from app.notifications import webhook as wh_module
    with patch("app.notifications.webhook.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(side_effect=httpx.ConnectError("refused"))
        await wh_module._post("https://hooks.slack.com/test", {"text": "hi"})
