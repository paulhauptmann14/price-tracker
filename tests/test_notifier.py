"""Tests for the notifier implementations."""

import logging

from pricewatch.core import NotifierPort
from pricewatch.notifier import (
    DesktopNotifier,
    FallbackNotifier,
    LogNotifier,
    MacNotifier,
    create_default_notifier,
)


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


class TestMacNotifier:
    def test_implements_notifier_port(self):
        assert isinstance(MacNotifier(), NotifierPort)

    def test_builds_osascript_display_notification_command(self):
        commands: list[list[str]] = []
        notifier = MacNotifier(runner=commands.append)
        notifier.notify("Price alert", "Book is now 8.99")
        assert len(commands) == 1
        cmd = commands[0]
        assert cmd[0] == "osascript"
        assert "-e" in cmd
        script = cmd[cmd.index("-e") + 1]
        assert 'display notification "Book is now 8.99" with title "Price alert"' == script

    def test_escapes_double_quotes_in_arguments(self):
        commands: list[list[str]] = []
        notifier = MacNotifier(runner=commands.append)
        notifier.notify('a "quoted" title', 'say "hi"')
        script = commands[0][commands[0].index("-e") + 1]
        assert r'\"quoted\"' in script
        assert r'\"hi\"' in script


class TestFallbackNotifier:
    def test_implements_notifier_port(self):
        assert isinstance(FallbackNotifier(LogNotifier(), LogNotifier()), NotifierPort)

    def test_uses_primary_when_it_succeeds(self):
        primary_calls, fallback_calls = [], []
        notifier = FallbackNotifier(
            primary=DesktopNotifier(backend=lambda t, m: primary_calls.append((t, m))),
            fallback=DesktopNotifier(backend=lambda t, m: fallback_calls.append((t, m))),
        )
        notifier.notify("T", "M")
        assert primary_calls == [("T", "M")]
        assert fallback_calls == []

    def test_falls_back_when_primary_raises(self):
        fallback_calls = []

        class Boom:
            def notify(self, title: str, message: str) -> None:
                raise RuntimeError("no backend")

        notifier = FallbackNotifier(
            primary=Boom(),
            fallback=DesktopNotifier(backend=lambda t, m: fallback_calls.append((t, m))),
        )
        notifier.notify("T", "M")
        assert fallback_calls == [("T", "M")]


class TestCreateDefaultNotifier:
    def test_darwin_uses_mac_notifier(self):
        notifier = create_default_notifier(platform="darwin")
        assert isinstance(notifier, FallbackNotifier)
        assert isinstance(notifier.primary, MacNotifier)

    def test_unknown_platform_uses_log_notifier(self):
        assert isinstance(create_default_notifier(platform="sunos"), LogNotifier)
