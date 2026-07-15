"""HTTP scraping with a flexible price-detection heuristic.

The scraper is split into three pieces that can be tested independently:

* ``parse_price``     -- turn a raw price string into a float, handling both
                         German (``1.299,00 €``) and US (``$1,299.00``) formats.
* ``extract_raw_price`` -- pull the raw price string out of an HTML document
                         using a fallback chain (CSS selector -> itemprop/meta
                         -> class/id containing price/preis -> currency regex).
* ``HttpScraper``     -- fetch the page (with a rotating User-Agent) and combine
                         the two functions above into a ``PriceResult``.

Network access is injected via ``fetch_html`` so the logic can be tested against
HTML fixtures without hitting the network.
"""

from __future__ import annotations

import random
import re
from typing import Callable

from bs4 import BeautifulSoup

from pricewatch.core import PriceResult, Product

# Common desktop browser User-Agents, rotated per request to reduce the chance
# of being blocked outright.
USER_AGENTS: list[str] = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) "
    "Gecko/20100101 Firefox/121.0",
]

# Matches the first number-like token, e.g. "1.299,00" or "9" inside free text.
_NUMBER_RE = re.compile(r"\d[\d.,]*\d|\d")

# Matches a currency amount with a symbol on either side, used as the last-resort
# extraction step.
_CURRENCY_RE = re.compile(r"[€$£]\s?\d[\d.,]*|\d[\d.,]*\s?[€$£]")

# Class/id substrings that typically wrap a price.
_PRICE_HINT_RE = re.compile(r"price|preis", re.IGNORECASE)

FetchHtml = Callable[[str], str]


def parse_price(text: str | None) -> float | None:
    """Parse a price string into a float, handling German and US formats.

    Returns ``None`` when no numeric value can be found.
    """
    if not text:
        return None
    match = _NUMBER_RE.search(text)
    if not match:
        return None
    token = match.group()

    if "." in token and "," in token:
        # Both separators present: the rightmost one is the decimal separator.
        if token.rfind(",") > token.rfind("."):
            token = token.replace(".", "").replace(",", ".")
        else:
            token = token.replace(",", "")
    elif "," in token:
        token = _normalize_single_separator(token, ",")
    elif "." in token:
        token = _normalize_single_separator(token, ".")

    try:
        return float(token)
    except ValueError:
        return None


def _normalize_single_separator(token: str, sep: str) -> str:
    """Normalize a token that contains only one kind of separator.

    Multiple occurrences are always thousands separators. A single occurrence
    followed by exactly three digits is treated as a thousands separator;
    otherwise it is the decimal separator.
    """
    if token.count(sep) > 1:
        return token.replace(sep, "")
    after = token.split(sep)[1]
    if len(after) == 3:
        return token.replace(sep, "")  # thousands grouping, e.g. "1.500"
    return token.replace(sep, ".")     # decimal, e.g. "9,99"


def extract_raw_price(html: str, css_selector: str | None = None) -> str | None:
    """Extract the raw price string from an HTML document.

    Fallback chain:
      1. an explicit CSS selector (if provided),
      2. ``itemprop="price"`` / ``<meta property="product:price:amount">``,
      3. an element whose class or id contains ``price`` or ``preis``,
      4. a currency pattern anywhere in the page text.
    """
    soup = BeautifulSoup(html, "html.parser")

    # 1. explicit selector
    if css_selector:
        element = soup.select_one(css_selector)
        if element is not None:
            return _text_or_content(element)

    # 2. structured metadata
    meta = soup.find("meta", attrs={"itemprop": "price"}) or soup.find(
        "meta", attrs={"property": "product:price:amount"}
    )
    if meta is not None and meta.get("content"):
        return meta["content"]
    itemprop = soup.find(attrs={"itemprop": "price"})
    if itemprop is not None:
        return _text_or_content(itemprop)

    # 3. class / id hints
    hinted = soup.find(class_=_PRICE_HINT_RE) or soup.find(id=_PRICE_HINT_RE)
    if hinted is not None:
        text = hinted.get_text(strip=True)
        if text:
            return text

    # 4. currency pattern in raw text
    match = _CURRENCY_RE.search(soup.get_text(" "))
    if match is not None:
        return match.group().strip()

    return None


def _text_or_content(element) -> str | None:
    """Return an element's text, or its ``content`` attribute if text is empty."""
    text = element.get_text(strip=True)
    if text:
        return text
    content = element.get("content")
    return content if content else None


class HttpScraper:
    """Fetches product pages and extracts prices (implements ScraperPort)."""

    def __init__(
        self,
        fetch_html: FetchHtml | None = None,
        user_agents: list[str] | None = None,
        timeout: float = 10.0,
    ) -> None:
        self._user_agents = user_agents or USER_AGENTS
        self._timeout = timeout
        self._fetch_html = fetch_html or self._default_fetch_html

    def fetch_price(self, product: Product) -> PriceResult:
        try:
            html = self._fetch_html(product.url)
        except Exception as exc:  # noqa: BLE001 - network errors are reported, not raised
            return PriceResult.failure(str(exc))

        raw = extract_raw_price(html, product.css_selector)
        if raw is None:
            return PriceResult.failure("no price found on page")

        value = parse_price(raw)
        if value is None:
            return PriceResult.failure(f"could not parse price: {raw!r}")

        return PriceResult.ok(value, raw=raw)

    def _default_fetch_html(self, url: str) -> str:
        # Imported lazily so the module (and its tests) do not require `requests`
        # unless a real network fetch is actually performed.
        import requests

        headers = {"User-Agent": random.choice(self._user_agents)}
        response = requests.get(url, headers=headers, timeout=self._timeout)
        response.raise_for_status()
        return response.text
