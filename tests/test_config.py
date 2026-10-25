from pathlib import Path

from camera_tracker.config import load_products, load_settings, load_watches


def test_default_products_include_bodies_and_trinity_lenses() -> None:
    products = load_products(Path("config/products.yaml"))
    ids = {product["id"] for product in products}
    assert {"sony-a7v", "canon-r5m2", "sony-fe-24-70-gm2", "canon-rf-24-70-l"} <= ids


def test_lenses_are_maintained_in_a_separate_config_file() -> None:
    bodies_text = Path("config/products.yaml").read_text(encoding="utf-8")
    lenses_text = Path("config/lenses.yaml").read_text(encoding="utf-8")

    assert "sony-fe-24-70-gm2" not in bodies_text
    assert "sony-fe-24-70-gm2" in lenses_text


def test_default_watches_use_declared_public_source_adapters() -> None:
    watches = load_watches(Path("config/watches.yaml"))
    assert {watch["platform"] for watch in watches} >= {"price_com_hk", "canon_cn", "sony_hk"}
    assert all(watch["url"].startswith("https://") for watch in watches)


def test_default_settings_configures_snapshot_retention() -> None:
    assert load_settings(Path("config/settings.yaml"))["snapshot_retention_days"] == 30
