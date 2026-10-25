from camera_tracker.notifications import send_webhook


def test_webhook_sends_structured_alert_payload() -> None:
    received: list[tuple[str, dict[str, object]]] = []

    send_webhook("https://notify.test", {"product": "Sony α7 V", "price": 19999}, lambda url, payload: received.append((url, payload)))

    assert received == [("https://notify.test", {"product": "Sony α7 V", "price": 19999})]
