import camera_tracker.catalog as catalog


def test_resolves_alias_and_typo_to_the_same_product() -> None:
    products = catalog.build_product_catalog(
        [
            {
                "id": "sony-a7v",
                "name": "Sony α7 V",
                "aliases": ["A7M5", "ILCE-7M5", "Sony A7V"],
            }
        ]
    )

    assert products.resolve("a7m5").id == "sony-a7v"
    assert products.resolve("Sony A7V").id == "sony-a7v"
