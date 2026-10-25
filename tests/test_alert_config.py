from pathlib import Path
from decimal import Decimal

from camera_tracker.config import load_target_prices


def test_target_prices_are_loaded_from_separate_config_file() -> None:
    targets = load_target_prices(Path("config/alerts.yaml"))

    assert targets["canon-r5m2"] == Decimal("30000")
