"""Tests for the price parser, extraction heuristic and HttpScraper."""

import pytest

from pricewatch.core import Product
from pricewatch.scraper import HttpScraper, extract_raw_price, parse_price


class TestParsePrice:
    @pytest.mark.parametrize(
        "text,expected",
        [
            ("1.299,00 €", 1299.00),   # German: dot=thousands, comma=decimal
            ("$1,299.00", 1299.00),    # US: comma=thousands, dot=decimal
            ("9,99 €", 9.99),          # German decimal comma
            ("19.99", 19.99),          # plain decimal dot
            ("1.500", 1500.0),         # German thousands, no decimals
            ("1,299", 1299.0),         # US thousands, no decimals
            ("1.234.567,89", 1234567.89),
            ("1,234,567.89", 1234567.89),
            ("100", 100.0),
            ("Now only 1.299,00 € (was 1.499,00)", 1299.00),  # first number wins
            ("€ 49,90", 49.90),
        ],
    )
    def test_parses_de_and_us_formats(self, text: str, expected: float):
        assert parse_price(text) == pytest.approx(expected)

    def test_returns_none_for_non_numeric(self):
        assert parse_price("no price here") is None

    def test_returns_none_for_empty(self):
        assert parse_price("") is None
        assert parse_price(None) is None


class TestExtractRawPrice:
    def test_uses_explicit_css_selector_first(self):
        html = """
        <div class="price">99,99 €</div>
        <span id="deal">1,00 €</span>
        """
        assert extract_raw_price(html, css_selector="#deal") == "1,00 €"

    def test_falls_back_to_itemprop_meta(self):
        html = '<meta itemprop="price" content="42.50">'
        assert extract_raw_price(html) == "42.50"

    def test_falls_back_to_class_containing_price(self):
        html = '<div><span class="product-price">12,34 €</span></div>'
        assert extract_raw_price(html) == "12,34 €"

    def test_falls_back_to_class_containing_preis(self):
        html = '<div class="aktueller-preis">7,77 €</div>'
        assert extract_raw_price(html) == "7,77 €"

    def test_falls_back_to_currency_regex_in_text(self):
        html = "<body><p>Great deal at 55,00 € today!</p></body>"
        assert extract_raw_price(html) is not None
        assert parse_price(extract_raw_price(html)) == pytest.approx(55.00)

    def test_returns_none_when_nothing_found(self):
        html = "<body><p>Sold out</p></body>"
        assert extract_raw_price(html) is None


class TestHttpScraperFetchPrice:
    def _product(self, css_selector: str | None = None) -> Product:
        return Product(
            id="1", name="Book", url="http://example.com/p",
            target_price=10.0, css_selector=css_selector,
        )

    def test_success_returns_ok_result(self):
        html = '<div class="price">8,99 €</div>'
        scraper = HttpScraper(fetch_html=lambda url: html)
        result = scraper.fetch_price(self._product())
        assert result.success is True
        assert result.value == pytest.approx(8.99)
        assert result.raw == "8,99 €"

    def test_network_error_returns_failure(self):
        def boom(url: str) -> str:
            raise ConnectionError("dns failure")

        scraper = HttpScraper(fetch_html=boom)
        result = scraper.fetch_price(self._product())
        assert result.success is False
        assert result.value is None
        assert "dns failure" in result.error

    def test_no_price_on_page_returns_failure(self):
        scraper = HttpScraper(fetch_html=lambda url: "<p>Sold out</p>")
        result = scraper.fetch_price(self._product())
        assert result.success is False
        assert result.error is not None

    def test_unparsable_price_returns_failure(self):
        html = '<div class="price">call for price</div>'
        scraper = HttpScraper(fetch_html=lambda url: html)
        result = scraper.fetch_price(self._product())
        assert result.success is False
