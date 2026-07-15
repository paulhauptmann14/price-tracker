"""JSON-based persistence for settings and products.

Stores everything in a single file (`products.json`) with the structure:

    { "settings": {...}, "products": [...] }

Writing is atomic (temp file + os.replace) so a crash mid-save cannot corrupt
the existing file. On load, missing or invalid files fall back to defaults
instead of crashing.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from pathlib import Path

from pricewatch.core import Product, ProductStatus, Settings

logger = logging.getLogger(__name__)


class JsonRepository:
    """Loads and saves the application state in a JSON file."""

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)

    def load(self) -> tuple[Settings, list[Product]]:
        if not self._path.exists():
            return Settings(), []
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Could not load %s (%s) -- using defaults.", self._path, exc)
            return Settings(), []

        settings = _settings_from_dict(data.get("settings", {}))
        products = [_product_from_dict(item) for item in data.get("products", [])]
        return settings, products

    def save(self, settings: Settings, products: list[Product]) -> None:
        data = {
            "settings": _settings_to_dict(settings),
            "products": [_product_to_dict(p) for p in products],
        }
        payload = json.dumps(data, indent=2, ensure_ascii=False)
        self._atomic_write(payload)

    def _atomic_write(self, payload: str) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        # temp file in the same directory so os.replace stays atomic
        fd, tmp_name = tempfile.mkstemp(
            dir=self._path.parent, prefix=self._path.name, suffix=".tmp"
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(payload)
            os.replace(tmp_name, self._path)
        except BaseException:
            # do not leave a temp file behind on error
            if os.path.exists(tmp_name):
                os.remove(tmp_name)
            raise


def _settings_to_dict(settings: Settings) -> dict:
    return {"poll_interval_minutes": settings.poll_interval_minutes}


def _settings_from_dict(data: dict) -> Settings:
    return Settings(
        poll_interval_minutes=data.get("poll_interval_minutes", Settings().poll_interval_minutes)
    )


def _product_to_dict(product: Product) -> dict:
    return {
        "id": product.id,
        "name": product.name,
        "url": product.url,
        "target_price": product.target_price,
        "css_selector": product.css_selector,
        "last_price": product.last_price,
        "status": product.status.value,
    }


def _product_from_dict(data: dict) -> Product:
    return Product(
        id=data["id"],
        name=data["name"],
        url=data["url"],
        target_price=data["target_price"],
        css_selector=data.get("css_selector"),
        last_price=data.get("last_price"),
        status=ProductStatus(data.get("status", ProductStatus.PENDING.value)),
    )
