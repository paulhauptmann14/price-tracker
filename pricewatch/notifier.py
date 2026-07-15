"""Notification backends (implementations of NotifierPort).

* ``LogNotifier``     -- writes notifications to the logging system. Useful as a
                         headless fallback and in tests.
* ``MacNotifier``     -- native macOS popup via ``osascript`` (no extra deps).
* ``DesktopNotifier`` -- cross-platform popup via ``plyer``. The actual backend
                         is injectable so it can be tested without a GUI.
* ``FallbackNotifier`` -- tries a primary notifier and, if it fails, a fallback.
* ``create_default_notifier`` -- picks a sensible notifier for the platform.
"""

from __future__ import annotations

import logging
import subprocess
import sys
from typing import Callable

from pricewatch.core import NotifierPort

logger = logging.getLogger(__name__)

NotifyBackend = Callable[[str, str], None]
CommandRunner = Callable[[list[str]], None]


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


class MacNotifier:
    """Notifier that shows a native macOS popup via ``osascript``."""

    def __init__(self, runner: CommandRunner | None = None) -> None:
        self._runner = runner or self._default_runner

    def notify(self, title: str, message: str) -> None:
        script = (
            f"display notification {_applescript_string(message)} "
            f"with title {_applescript_string(title)}"
        )
        self._runner(["osascript", "-e", script])

    def _default_runner(self, command: list[str]) -> None:
        subprocess.run(command, check=True, capture_output=True)


class FallbackNotifier:
    """Tries a primary notifier, falling back to another if it raises."""

    def __init__(self, primary: NotifierPort, fallback: NotifierPort) -> None:
        self.primary = primary
        self.fallback = fallback

    def notify(self, title: str, message: str) -> None:
        try:
            self.primary.notify(title, message)
        except Exception as exc:  # noqa: BLE001 - the whole point is to degrade gracefully
            logger.warning("Primary notifier failed (%s); using fallback.", exc)
            self.fallback.notify(title, message)


def create_default_notifier(platform: str | None = None) -> NotifierPort:
    """Return a sensible notifier for the given platform (defaults to this host)."""
    platform = platform if platform is not None else sys.platform
    if platform == "darwin":
        return FallbackNotifier(MacNotifier(), LogNotifier())
    if platform in ("win32", "linux"):
        return FallbackNotifier(DesktopNotifier(), LogNotifier())
    return LogNotifier()


def _applescript_string(value: str) -> str:
    """Quote and escape a Python string as an AppleScript string literal."""
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'
