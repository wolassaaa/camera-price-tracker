"""Notification policies and transports."""

from datetime import datetime, timedelta
from collections.abc import Callable
from dataclasses import dataclass
from email.message import EmailMessage
import os
import smtplib

import httpx


class NotificationDeduper:
    def __init__(self, *, cooldown: timedelta) -> None:
        self.cooldown = cooldown
        self._sent: dict[tuple[str, str], datetime] = {}

    def should_send(self, product_id: str, alert_type: str, now: datetime) -> bool:
        key = (product_id, alert_type)
        previous = self._sent.get(key)
        if previous is not None and now - previous < self.cooldown:
            return False
        self._sent[key] = now
        return True


@dataclass(frozen=True)
class NotificationConfig:
    webhook_url: str | None = None
    pushplus_token: str | None = None
    telegram_bot_token: str | None = None
    telegram_chat_id: str | None = None
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_to: str | None = None
    windows_desktop_enabled: bool = False

    @classmethod
    def from_env(cls) -> "NotificationConfig":
        return cls(
            webhook_url=os.getenv("WEBHOOK_URL") or None,
            pushplus_token=os.getenv("PUSHPLUS_TOKEN") or None,
            telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN") or None,
            telegram_chat_id=os.getenv("TELEGRAM_CHAT_ID") or None,
            smtp_host=os.getenv("SMTP_HOST") or None,
            smtp_port=int(os.getenv("SMTP_PORT", "587")),
            smtp_username=os.getenv("SMTP_USERNAME") or None,
            smtp_password=os.getenv("SMTP_PASSWORD") or None,
            smtp_to=os.getenv("SMTP_TO") or None,
            windows_desktop_enabled=os.getenv("WINDOWS_DESKTOP_NOTIFICATIONS", "false").lower() == "true",
        )


def _title(payload: dict[str, object]) -> str:
    return f"相机价格监控：{payload.get('event', '通知')}"


def _body(payload: dict[str, object]) -> str:
    return "\n".join(f"{key}: {value}" for key, value in payload.items())


def send_webhook(
    url: str, payload: dict[str, object],
    post: Callable[[str, dict[str, object]], object] | None = None,
) -> None:
    """Send only to a user-configured endpoint; secrets stay in environment config."""
    if post is not None:
        post(url, payload)
        return
    response = httpx.post(url, json=payload, timeout=15)
    response.raise_for_status()


def send_pushplus(token: str, payload: dict[str, object], *, post: Callable[..., object] = httpx.post) -> None:
    response = post(
        "https://www.pushplus.plus/send",
        json={"token": token, "title": _title(payload), "content": _body(payload), "template": "txt"}, timeout=15,
    )
    response.raise_for_status()


def send_telegram(
    bot_token: str, chat_id: str, payload: dict[str, object], *, post: Callable[..., object] = httpx.post,
) -> None:
    response = post(
        f"https://api.telegram.org/bot{bot_token}/sendMessage",
        json={"chat_id": chat_id, "text": f"{_title(payload)}\n{_body(payload)}"}, timeout=15,
    )
    response.raise_for_status()


def send_email(config: NotificationConfig, payload: dict[str, object], *, smtp_factory: Callable[..., object] = smtplib.SMTP) -> None:
    if not (config.smtp_host and config.smtp_to):
        return
    message = EmailMessage()
    message["Subject"] = _title(payload)
    message["From"] = config.smtp_username or "camera-price-tracker@localhost"
    message["To"] = config.smtp_to
    message.set_content(_body(payload))
    with smtp_factory(config.smtp_host, config.smtp_port, timeout=15) as client:
        client.starttls()
        if config.smtp_username and config.smtp_password:
            client.login(config.smtp_username, config.smtp_password)
        client.send_message(message)


def send_windows_desktop(payload: dict[str, object]) -> bool:
    """Use the optional plyer backend; unavailable backends simply do not send."""
    try:
        from plyer import notification
        notification.notify(title=_title(payload), message=_body(payload), app_name="Camera Price Tracker", timeout=10)
    except (ImportError, OSError):
        return False
    return True


def send_all(config: NotificationConfig, payload: dict[str, object]) -> list[str]:
    """Fan out only to user-configured local notification destinations."""
    delivered: list[str] = []
    if config.webhook_url:
        send_webhook(config.webhook_url, payload)
        delivered.append("webhook")
    if config.pushplus_token:
        send_pushplus(config.pushplus_token, payload)
        delivered.append("pushplus")
    if config.telegram_bot_token and config.telegram_chat_id:
        send_telegram(config.telegram_bot_token, config.telegram_chat_id, payload)
        delivered.append("telegram")
    if config.smtp_host and config.smtp_to:
        send_email(config, payload)
        delivered.append("email")
    if config.windows_desktop_enabled and send_windows_desktop(payload):
        delivered.append("windows_desktop")
    return delivered
