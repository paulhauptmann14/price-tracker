"""Notification backends (implementations of NotifierPort).

* ``LogNotifier``     -- writes notifications to the logging system. Useful as a
                         headless fallback and in tests.
* ``DesktopNotifier`` -- shows a native desktop popup via ``plyer``. The actual
                         backend is injectable so it can be tested without a GUI
                         and without requiring ``plyer`` to be installed.
"""

from __future__ import annotations

import logging
from typing import Callable

logger = logging.getLogger(__name__)

NotifyBackend = Callable[[str, str], None]


class LogNotifier:
    """Notifier that writes to the logging system."""

    def __init__(self, log: logging.Logger | None = None) -> None:
        self._log = log or logger

    def notify(self, title: str, message: str) -> None:
        self._log.info("%s: %s", title, message)


class DesktopNotifier:
    """Notifier that shows a native desktop popup via plyer."""

    def __init__(self, backend: NotifyBackend | None = None, app_name: str = "Price Tracker") -> None:
        self._backend = backend
        self._app_name = app_name

    def notify(self, title: str, message: str) -> None:
        backend = self._backend or self._default_backend
        backend(title, message)

    def _default_backend(self, title: str, message: str) -> None:
        # Imported lazily so tests and headless use do not require `plyer`.
        from plyer import notification

        notification.notify(title=title, message=message, app_name=self._app_name)
