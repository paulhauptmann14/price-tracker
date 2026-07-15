"""Tests for the domain models and ports in pricewatch.core."""

from pricewatch.core import (
    NotifierPort,
    PriceResult,
    Product,
    ProductStatus,
    RepositoryPort,
    ScraperPort,
    Settings,
)


class TestProduct:
    def test_new_product_has_sensible_defaults(self):
        product = Product(id="1", name="Buch", url="http://x", target_price=10.0)
        assert product.css_selector is None
        assert product.last_price is None
        assert product.status is ProductStatus.PENDING

    def test_evaluate_returns_target_reached_when_price_at_or_below_target(self):
        product = Product(id="1", name="Buch", url="http://x", target_price=10.0)
        assert product.evaluate(10.0) is ProductStatus.TARGET_REACHED
        assert product.evaluate(9.99) is ProductStatus.TARGET_REACHED

    def test_evaluate_returns_ok_when_price_above_target(self):
        product = Product(id="1", name="Buch", url="http://x", target_price=10.0)
        assert product.evaluate(10.01) is ProductStatus.OK


class TestPriceResult:
    def test_ok_factory_marks_success(self):
        result = PriceResult.ok(12.5, raw="12,50 €")
        assert result.success is True
        assert result.value == 12.5
        assert result.raw == "12,50 €"
        assert result.error is None

    def test_failure_factory_marks_failure(self):
        result = PriceResult.failure("timeout")
        assert result.success is False
        assert result.value is None
        assert result.error == "timeout"


class TestSettings:
    def test_default_poll_interval(self):
        assert Settings().poll_interval_minutes == 60


class TestPorts:
    def test_conforming_class_satisfies_scraper_port(self):
        class DummyScraper:
            def fetch_price(self, product: Product) -> PriceResult:
                return PriceResult.ok(1.0, raw="1")

        assert isinstance(DummyScraper(), ScraperPort)

    def test_conforming_class_satisfies_notifier_port(self):
        class DummyNotifier:
            def notify(self, title: str, message: str) -> None:
                return None

        assert isinstance(DummyNotifier(), NotifierPort)

    def test_conforming_class_satisfies_repository_port(self):
        class DummyRepo:
            def load(self) -> tuple[Settings, list[Product]]:
                return Settings(), []

            def save(self, settings: Settings, products: list[Product]) -> None:
                return None

        assert isinstance(DummyRepo(), RepositoryPort)

    def test_nonconforming_class_fails_scraper_port(self):
        class NotAScraper:
            pass

        assert not isinstance(NotAScraper(), ScraperPort)
