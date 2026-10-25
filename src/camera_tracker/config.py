"""Configuration loading."""

from pathlib import Path
from decimal import Decimal

import yaml


def load_products(path: Path) -> list[dict[str, object]]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    lenses_path = path.parent / "lenses.yaml"
    lenses_data = yaml.safe_load(lenses_path.read_text(encoding="utf-8")) if lenses_path.exists() else {}
    return [*list(data.get("products", [])), *list((lenses_data or {}).get("lenses", []))]


def save_products(path: Path, products: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    bodies = [product for product in products if product.get("type") != "lens"]
    lenses = [product for product in products if product.get("type") == "lens"]
    path.write_text(
        yaml.safe_dump({"products": bodies}, allow_unicode=True, sort_keys=False), encoding="utf-8",
    )
    (path.parent / "lenses.yaml").write_text(
        yaml.safe_dump({"lenses": lenses}, allow_unicode=True, sort_keys=False), encoding="utf-8",
    )


def load_watches(path: Path) -> list[dict[str, str]]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return list(data.get("watches", []))


def save_watches(path: Path, watches: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump({"watches": watches}, allow_unicode=True, sort_keys=False), encoding="utf-8",
    )


def load_events(path: Path) -> list[dict[str, object]]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return list(data.get("events", []))


def save_events(path: Path, events: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump({"events": events}, allow_unicode=True, sort_keys=False), encoding="utf-8",
    )


def load_sources(path: Path) -> dict[str, dict[str, object]]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return dict(data.get("sources", {}))


def save_sources(path: Path, sources: dict[str, dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump({"sources": sources}, allow_unicode=True, sort_keys=False), encoding="utf-8",
    )


def load_target_prices(path: Path) -> dict[str, Decimal]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return {str(item["product_id"]): Decimal(str(item["target_price_cny"])) for item in data.get("targets", [])}


def save_target_prices(path: Path, targets: dict[str, Decimal]) -> None:
    """Persist only explicit target prices; callers validate product ids first."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "targets": [
            {"product_id": product_id, "target_price_cny": str(price)}
            for product_id, price in sorted(targets.items())
        ]
    }
    path.write_text(yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), encoding="utf-8")


def load_settings(path: Path) -> dict[str, object]:
    return dict(yaml.safe_load(path.read_text(encoding="utf-8")) or {})


def save_settings(path: Path, settings: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(settings, allow_unicode=True, sort_keys=False), encoding="utf-8")
