"""Domain models and ports (protocols) for the price tracker.

This module is the UI-agnostic core. It has no dependencies on infrastructure
(network, filesystem, GUI) -- only pure data structures and the abstract
interfaces (ports) that everything else is programmed against.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Protocol, runtime_checkable


class ProductStatus(str, Enum):
    """State of a monitored product."""

    PENDING = "pending"                 # never successfully fetched yet
    OK = "ok"                           # price fetched, above target
    TARGET_REACHED = "target_reached"   # price <= target
    ERROR = "error"                     # last fetch failed


@dataclass
class Product:
    """A product to monitor."""

    id: str
    name: str
    url: str
    target_price: float
    css_selector: str | None = None
    last_price: float | None = None
    status: ProductStatus = ProductStatus.PENDING

    def evaluate(self, price: float) -> ProductStatus:
        """Return the status for a freshly fetched price."""
        if price <= self.target_price:
            return ProductStatus.TARGET_REACHED
        return ProductStatus.OK


@dataclass
class PriceResult:
    """Outcome of a single price fetch."""

    success: bool
    value: float | None = None
    raw: str | None = None
    error: str | None = None

    @classmethod
    def ok(cls, value: float, raw: str | None = None) -> PriceResult:
        return cls(success=True, value=value, raw=raw)

    @classmethod
    def failure(cls, error: str) -> PriceResult:
        return cls(success=False, error=error)


@dataclass
class Settings:
    """Application settings."""

    poll_interval_minutes: int = 60


@runtime_checkable
class ScraperPort(Protocol):
    """Fetches the current price for a product."""

    def fetch_price(self, product: Product) -> PriceResult: ...


@runtime_checkable
class NotifierPort(Protocol):
    """Sends a notification to the user."""

    def notify(self, title: str, message: str) -> None: ...


@runtime_checkable
class RepositoryPort(Protocol):
    """Loads and saves settings and products."""

    def load(self) -> tuple[Settings, list[Product]]: ...

    def save(self, settings: Settings, products: list[Product]) -> None: ...
