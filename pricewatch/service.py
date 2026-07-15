"""Application facade and background monitoring engine.

``MonitorService`` is the single entry point the presentation layer (CLI, GUI or
a future web frontend) talks to. It owns the product list and settings, performs
price checks, and runs the polling loop in a background thread so the UI never
blocks.

Results are reported through an ``on_update`` callback rather than pushed to any
specific UI, keeping the service presentation-agnostic. Thread-safety of the
callback (e.g. marshalling onto a GUI event loop) is the presentation's concern.
"""

from __future__ import annotations

import logging
import threading
import uuid
from typing import Callable

from pricewatch.core import (
    NotifierPort,
    Product,
    ProductStatus,
    RepositoryPort,
    ScraperPort,
    Settings,
)

logger = logging.getLogger(__name__)

OnUpdate = Callable[[Product], None]


class MonitorService:
    """Facade over scraping, persistence and notification with a polling thread."""

    def __init__(
        self,
        repository: RepositoryPort,
        scraper: ScraperPort,
        notifier: NotifierPort,
        on_update: OnUpdate | None = None,
    ) -> None:
        self._repository = repository
        self._scraper = scraper
        self._notifier = notifier
        self._on_update = on_update or (lambda product: None)

        self._settings, self._products = repository.load()
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    # -- product management ------------------------------------------------

    def list_products(self) -> list[Product]:
        with self._lock:
            return list(self._products)

    def add_product(
        self,
        name: str,
        url: str,
        target_price: float,
        css_selector: str | None = None,
    ) -> Product:
        product = Product(
            id=uuid.uuid4().hex,
            name=name,
            url=url,
            target_price=target_price,
            css_selector=css_selector,
        )
        with self._lock:
            self._products.append(product)
        self._persist()
        return product

    def remove_product(self, product_id: str) -> None:
        with self._lock:
            self._products = [p for p in self._products if p.id != product_id]
        self._persist()

    # -- settings ----------------------------------------------------------

    def get_settings(self) -> Settings:
        return self._settings

    def set_poll_interval(self, minutes: int) -> None:
        self._settings.poll_interval_minutes = minutes
        self._persist()

    # -- price checks ------------------------------------------------------

    def check_product(self, product: Product) -> None:
        """Fetch the current price for one product and update its state."""
        previous_status = product.status
        result = self._scraper.fetch_price(product)

        if result.success and result.value is not None:
            product.last_price = result.value
            product.status = product.evaluate(result.value)
            if (
                product.status is ProductStatus.TARGET_REACHED
                and previous_status is not ProductStatus.TARGET_REACHED
            ):
                self._notify_target_reached(product)
        else:
            product.status = ProductStatus.ERROR
            logger.warning("Fetch failed for %s: %s", product.name, result.error)

        self._persist()
        self._on_update(product)

    def check_all(self) -> None:
        """Run one polling pass over all products."""
        for product in self.list_products():
            if self._stop_event.is_set():
                break
            self.check_product(product)

    # -- monitoring thread -------------------------------------------------

    def start(self) -> None:
        """Start the background polling loop (idempotent)."""
        if self.is_running():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, name="pricewatch-monitor", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Signal the polling loop to stop and wait for it to finish."""
        self._stop_event.set()
        thread = self._thread
        if thread is not None:
            thread.join()
            self._thread = None

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def _run(self) -> None:
        while not self._stop_event.is_set():
            self.check_all()
            # Wait for the configured interval, but wake up immediately on stop.
            self._stop_event.wait(self._interval_seconds())

    def _interval_seconds(self) -> float:
        return max(1, self._settings.poll_interval_minutes) * 60

    # -- helpers -----------------------------------------------------------

    def _notify_target_reached(self, product: Product) -> None:
        # A failing notification must never abort the monitoring loop: the price
        # update matters more than the popup. Log and carry on.
        try:
            self._notifier.notify(
                "Price alert",
                f"{product.name} is now {product.last_price} (target {product.target_price})",
            )
        except Exception as exc:  # noqa: BLE001 - defensive: any backend failure is non-fatal
            logger.warning("Notification failed for %s: %s", product.name, exc)

    def _persist(self) -> None:
        with self._lock:
            self._repository.save(self._settings, list(self._products))
