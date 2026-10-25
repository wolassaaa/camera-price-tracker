from datetime import datetime, timedelta, timezone

from camera_tracker.notifications import NotificationConfig, NotificationDeduper, send_pushplus, send_telegram


def test_identical_alert_is_suppressed_inside_cooldown() -> None:
    deduper = NotificationDeduper(cooldown=timedelta(hours=6))
    now = datetime(2026, 7, 23, tzinfo=timezone.utc)

    assert deduper.should_send("sony-a7v", "target-price", now) is True
    assert deduper.should_send("sony-a7v", "target-price", now + timedelta(minutes=10)) is False


class _Response:
    def raise_for_status(self) -> None:
        return None


def test_pushplus_and_telegram_use_structured_user_configured_transports() -> None:
    calls: list[tuple[str, dict[str, object]]] = []

    def post(url, *, json, timeout):
        calls.append((url, json))
        assert timeout == 15
        return _Response()

    payload = {"event": "price_drop", "product": "Sony α1", "current_price": "20000"}
    send_pushplus("token", payload, post=post)
    send_telegram("bot-token", "chat-id", payload, post=post)

    assert calls[0][0] == "https://www.pushplus.plus/send"
    assert calls[0][1]["token"] == "token"
    assert calls[1][0].endswith("/botbot-token/sendMessage")
    assert calls[1][1]["chat_id"] == "chat-id"


def test_notification_config_reads_only_local_environment_values(monkeypatch) -> None:
    monkeypatch.setenv("PUSHPLUS_TOKEN", "local-token")
    monkeypatch.setenv("WINDOWS_DESKTOP_NOTIFICATIONS", "true")

    config = NotificationConfig.from_env()

    assert config.pushplus_token == "local-token"
    assert config.windows_desktop_enabled is True
