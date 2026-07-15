"""Tests for the notifier implementations."""

import logging

from pricewatch.core import NotifierPort
from pricewatch.notifier import DesktopNotifier, LogNotifier


class TestLogNotifier:
    def test_implements_notifier_port(self):
        assert isinstance(LogNotifier(), NotifierPort)

    def test_logs_title_and_message(self, caplog):
        notifier = LogNotifier()
        with caplog.at_level(logging.INFO):
            notifier.notify("Price alert", "Book is now 8.99")
        assert "Price alert" in caplog.text
        assert "Book is now 8.99" in caplog.text


class TestDesktopNotifier:
    def test_implements_notifier_port(self):
        assert isinstance(DesktopNotifier(), NotifierPort)

    def test_calls_injected_backend_with_title_and_message(self):
        calls = []
        notifier = DesktopNotifier(backend=lambda title, message: calls.append((title, message)))
        notifier.notify("Price alert", "Book is now 8.99")
        assert calls == [("Price alert", "Book is now 8.99")]
