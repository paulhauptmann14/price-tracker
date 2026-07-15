"""Tests for the JSON persistence in pricewatch.repository."""

from pathlib import Path

from pricewatch.core import Product, ProductStatus, Settings
from pricewatch.repository import JsonRepository


class TestLoadDefaults:
    def test_missing_file_returns_defaults(self, tmp_path: Path):
        repo = JsonRepository(tmp_path / "products.json")
        settings, products = repo.load()
        assert settings == Settings()
        assert products == []

    def test_corrupt_file_returns_defaults(self, tmp_path: Path):
        path = tmp_path / "products.json"
        path.write_text("{ this is not valid json ", encoding="utf-8")
        repo = JsonRepository(path)
        settings, products = repo.load()
        assert settings == Settings()
        assert products == []


class TestRoundTrip:
    def test_save_then_load_restores_settings_and_products(self, tmp_path: Path):
        path = tmp_path / "products.json"
        repo = JsonRepository(path)
        settings = Settings(poll_interval_minutes=15)
        products = [
            Product(
                id="1",
                name="Buch",
                url="http://example.com/buch",
                target_price=9.99,
                css_selector=".price",
                last_price=12.50,
                status=ProductStatus.OK,
            ),
            Product(id="2", name="Stift", url="http://example.com/stift", target_price=1.0),
        ]

        repo.save(settings, products)
        loaded_settings, loaded_products = repo.load()

        assert loaded_settings == settings
        assert loaded_products == products

    def test_status_roundtrips_as_enum(self, tmp_path: Path):
        path = tmp_path / "products.json"
        repo = JsonRepository(path)
        product = Product(
            id="1", name="Buch", url="http://x", target_price=5.0,
            status=ProductStatus.TARGET_REACHED,
        )
        repo.save(Settings(), [product])
        _, loaded = repo.load()
        assert loaded[0].status is ProductStatus.TARGET_REACHED


class TestFileFormat:
    def test_file_is_readable_json_with_expected_structure(self, tmp_path: Path):
        import json

        path = tmp_path / "products.json"
        repo = JsonRepository(path)
        repo.save(Settings(30), [Product("1", "Buch", "http://x", 9.99)])

        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["settings"]["poll_interval_minutes"] == 30
        assert isinstance(data["products"], list)
        assert data["products"][0]["name"] == "Buch"

    def test_repeated_save_leaves_single_file(self, tmp_path: Path):
        path = tmp_path / "products.json"
        repo = JsonRepository(path)
        repo.save(Settings(), [Product("1", "Buch", "http://x", 9.99)])
        repo.save(Settings(), [Product("2", "Stift", "http://y", 1.0)])

        # atomic write: no temp leftovers, exactly one file
        json_files = list(tmp_path.iterdir())
        assert json_files == [path]
