"""Tests for the command-line interface."""

from pathlib import Path

from pricewatch.core import PriceResult, Product, ProductStatus
from pricewatch.notifier import LogNotifier
from pricewatch.repository import JsonRepository
from pricewatch.cli import create_service, main
from pricewatch.service import MonitorService


class FakeScraper:
    def __init__(self, price: float = 5.0):
        self._price = price

    def fetch_price(self, product: Product) -> PriceResult:
        return PriceResult.ok(self._price, raw=str(self._price))


def make_service(tmp_path: Path, price: float = 5.0) -> MonitorService:
    return MonitorService(
        repository=JsonRepository(tmp_path / "products.json"),
        scraper=FakeScraper(price),
        notifier=LogNotifier(),
    )


class TestAdd:
    def test_add_creates_and_reports_product(self, tmp_path, capsys):
        service = make_service(tmp_path)
        exit_code = main(
            ["add", "--name", "Book", "--url", "http://x", "--target-price", "9.99"],
            service=service,
        )
        assert exit_code == 0
        assert service.list_products()[0].name == "Book"
        assert "Book" in capsys.readouterr().out

    def test_add_accepts_optional_selector(self, tmp_path):
        service = make_service(tmp_path)
        main(
            ["add", "--name", "Book", "--url", "http://x",
             "--target-price", "9.99", "--selector", ".price"],
            service=service,
        )
        assert service.list_products()[0].css_selector == ".price"


class TestList:
    def test_list_shows_products(self, tmp_path, capsys):
        service = make_service(tmp_path)
        service.add_product("Book", "http://x", 9.99)
        main(["list"], service=service)
        out = capsys.readouterr().out
        assert "Book" in out
        assert "http://x" in out

    def test_list_empty_is_friendly(self, tmp_path, capsys):
        service = make_service(tmp_path)
        main(["list"], service=service)
        assert capsys.readouterr().out.strip() != ""


class TestRemove:
    def test_remove_deletes_product(self, tmp_path):
        service = make_service(tmp_path)
        product = service.add_product("Book", "http://x", 9.99)
        main(["remove", "--id", product.id], service=service)
        assert service.list_products() == []


class TestSetInterval:
    def test_set_interval_updates_settings(self, tmp_path):
        service = make_service(tmp_path)
        main(["set-interval", "--minutes", "5"], service=service)
        assert service.get_settings().poll_interval_minutes == 5


class TestCheck:
    def test_check_updates_prices_and_prints(self, tmp_path, capsys):
        service = make_service(tmp_path, price=8.0)
        service.add_product("Book", "http://x", target_price=10.0)
        main(["check"], service=service)
        product = service.list_products()[0]
        assert product.last_price == 8.0
        assert product.status is ProductStatus.TARGET_REACHED
        assert "Book" in capsys.readouterr().out


class TestCreateService:
    def test_create_service_wires_json_repository(self, tmp_path):
        path = tmp_path / "products.json"
        service = create_service(path)
        assert isinstance(service, MonitorService)
        service.add_product("Book", "http://x", 9.99)
        # persisted to the given path
        assert JsonRepository(path).load()[1][0].name == "Book"


class TestUnknownCommand:
    def test_no_command_prints_help_and_returns_nonzero(self, tmp_path, capsys):
        service = make_service(tmp_path)
        exit_code = main([], service=service)
        assert exit_code != 0
