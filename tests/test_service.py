"""Tests for the MonitorService: product management, polling and threading."""

import threading
from pathlib import Path

from pricewatch.core import PriceResult, Product, ProductStatus, Settings
from pricewatch.repository import JsonRepository
from pricewatch.service import MonitorService


class FakeRepository:
    """In-memory repository capturing the last saved state."""

    def __init__(self, settings: Settings | None = None, products: list[Product] | None = None):
        self._settings = settings or Settings()
        self._products = products or []
        self.save_count = 0

    def load(self) -> tuple[Settings, list[Product]]:
        return self._settings, list(self._products)

    def save(self, settings: Settings, products: list[Product]) -> None:
        self._settings = settings
        self._products = list(products)
        self.save_count += 1


class FakeScraper:
    """Scraper returning a fixed price (or failure) for every product."""

    def __init__(self, price: float | None = None, error: str | None = None):
        self._price = price
        self._error = error
        self.calls = 0

    def fetch_price(self, product: Product) -> PriceResult:
        self.calls += 1
        if self._error is not None:
            return PriceResult.failure(self._error)
        return PriceResult.ok(self._price, raw=str(self._price))


class RecordingNotifier:
    def __init__(self):
        self.notifications: list[tuple[str, str]] = []

    def notify(self, title: str, message: str) -> None:
        self.notifications.append((title, message))


def make_service(**kwargs) -> MonitorService:
    return MonitorService(
        repository=kwargs.get("repository", FakeRepository()),
        scraper=kwargs.get("scraper", FakeScraper(price=5.0)),
        notifier=kwargs.get("notifier", RecordingNotifier()),
        on_update=kwargs.get("on_update"),
    )


class TestProductManagement:
    def test_add_product_appears_in_list(self):
        service = make_service()
        product = service.add_product("Book", "http://x", target_price=10.0)
        assert product in service.list_products()
        assert product.name == "Book"

    def test_add_product_generates_unique_ids(self):
        service = make_service()
        a = service.add_product("A", "http://a", 1.0)
        b = service.add_product("B", "http://b", 2.0)
        assert a.id != b.id

    def test_remove_product(self):
        service = make_service()
        product = service.add_product("Book", "http://x", 10.0)
        service.remove_product(product.id)
        assert product not in service.list_products()

    def test_add_product_persists(self):
        repo = FakeRepository()
        service = make_service(repository=repo)
        service.add_product("Book", "http://x", 10.0)
        assert repo.save_count >= 1
        assert repo.load()[1][0].name == "Book"

    def test_loads_existing_products_on_init(self):
        existing = Product(id="1", name="Old", url="http://x", target_price=1.0)
        repo = FakeRepository(products=[existing])
        service = make_service(repository=repo)
        assert service.list_products()[0].name == "Old"


class TestSettings:
    def test_set_poll_interval_persists(self):
        repo = FakeRepository()
        service = make_service(repository=repo)
        service.set_poll_interval(15)
        assert service.get_settings().poll_interval_minutes == 15
        assert repo.load()[0].poll_interval_minutes == 15


class TestCheckProduct:
    def test_successful_check_updates_price_and_status(self):
        service = make_service(scraper=FakeScraper(price=8.0))
        product = service.add_product("Book", "http://x", target_price=10.0)
        service.check_product(product)
        assert product.last_price == 8.0
        assert product.status is ProductStatus.TARGET_REACHED

    def test_price_above_target_is_ok(self):
        service = make_service(scraper=FakeScraper(price=12.0))
        product = service.add_product("Book", "http://x", target_price=10.0)
        service.check_product(product)
        assert product.status is ProductStatus.OK

    def test_failed_fetch_sets_error_status(self):
        service = make_service(scraper=FakeScraper(error="timeout"))
        product = service.add_product("Book", "http://x", target_price=10.0)
        service.check_product(product)
        assert product.status is ProductStatus.ERROR

    def test_notifies_when_target_reached(self):
        notifier = RecordingNotifier()
        service = make_service(scraper=FakeScraper(price=8.0), notifier=notifier)
        product = service.add_product("Book", "http://x", target_price=10.0)
        service.check_product(product)
        assert len(notifier.notifications) == 1

    def test_does_not_renotify_while_already_target_reached(self):
        notifier = RecordingNotifier()
        service = make_service(scraper=FakeScraper(price=8.0), notifier=notifier)
        product = service.add_product("Book", "http://x", target_price=10.0)
        service.check_product(product)
        service.check_product(product)
        assert len(notifier.notifications) == 1

    def test_calls_on_update_callback(self):
        updated: list[Product] = []
        service = make_service(scraper=FakeScraper(price=8.0), on_update=updated.append)
        product = service.add_product("Book", "http://x", target_price=10.0)
        service.check_product(product)
        assert updated and updated[-1] is product


class RaisingNotifier:
    """Notifier whose backend always fails (e.g. no display available)."""

    def notify(self, title: str, message: str) -> None:
        raise RuntimeError("notification backend unavailable")


class TestNotifierRobustness:
    def test_notifier_failure_does_not_crash_check(self):
        service = make_service(scraper=FakeScraper(price=8.0), notifier=RaisingNotifier())
        product = service.add_product("Book", "http://x", target_price=10.0)
        # must not raise even though the notifier blows up
        service.check_product(product)
        assert product.last_price == 8.0
        assert product.status is ProductStatus.TARGET_REACHED

    def test_notifier_failure_does_not_stop_the_loop(self):
        updated: list[Product] = []
        service = make_service(
            scraper=FakeScraper(price=8.0),
            notifier=RaisingNotifier(),
            on_update=updated.append,
        )
        service.add_product("A", "http://a", target_price=10.0)
        service.add_product("B", "http://b", target_price=10.0)
        service.check_all()
        # both products were processed despite the notifier failing on each
        assert len(updated) == 2


class TestThreading:
    def test_start_runs_at_least_one_pass_then_stop(self):
        passed = threading.Event()
        service = make_service(
            scraper=FakeScraper(price=5.0),
            on_update=lambda p: passed.set(),
        )
        service.add_product("Book", "http://x", target_price=10.0)
        service.start()
        try:
            assert passed.wait(2.0), "monitoring pass did not run"
            assert service.is_running()
        finally:
            service.stop()
        assert not service.is_running()

    def test_start_is_idempotent(self):
        service = make_service()
        service.add_product("Book", "http://x", 10.0)
        service.start()
        try:
            thread = service._thread
            service.start()
            assert service._thread is thread
        finally:
            service.stop()

    def test_stop_when_not_running_is_safe(self):
        service = make_service()
        service.stop()  # should not raise
        assert not service.is_running()


class TestIntegrationWithJsonRepository:
    def test_end_to_end_persistence(self, tmp_path: Path):
        path = tmp_path / "products.json"
        service = MonitorService(
            repository=JsonRepository(path),
            scraper=FakeScraper(price=8.0),
            notifier=RecordingNotifier(),
        )
        product = service.add_product("Book", "http://x", target_price=10.0)
        service.check_product(product)

        # a fresh service over the same file sees the persisted state
        reloaded = MonitorService(
            repository=JsonRepository(path),
            scraper=FakeScraper(price=8.0),
            notifier=RecordingNotifier(),
        )
        stored = reloaded.list_products()[0]
        assert stored.last_price == 8.0
        assert stored.status is ProductStatus.TARGET_REACHED
