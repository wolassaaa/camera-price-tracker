"""Product catalog primitives."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Product:
    id: str
    name: str
    aliases: tuple[str, ...]


class ProductCatalog:
    def __init__(self, products: list[Product]) -> None:
        self._by_alias = {
            alias.casefold(): product
            for product in products
            for alias in (product.name, *product.aliases)
        }

    def resolve(self, value: str) -> Product:
        return self._by_alias[value.casefold()]


def build_product_catalog(items: list[dict[str, object]]) -> ProductCatalog:
    return ProductCatalog(
        [
            Product(
                id=str(item["id"]),
                name=str(item["name"]),
                aliases=tuple(str(alias) for alias in item.get("aliases", [])),
            )
            for item in items
        ]
    )
