"""Command-line interface for the price tracker.

A thin presentation layer over ``MonitorService``. It lets you manage products,
run a one-off check, or start the continuous monitoring loop -- enough to use
the tool end-to-end before a GUI exists.

Usage examples::

    python -m pricewatch.cli add --name "Book" --url https://... --target-price 9.99
    python -m pricewatch.cli list
    python -m pricewatch.cli check
    python -m pricewatch.cli run
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from pricewatch.core import Product
from pricewatch.notifier import create_default_notifier
from pricewatch.repository import JsonRepository
from pricewatch.scraper import HttpScraper
from pricewatch.service import MonitorService, OnUpdate

DEFAULT_DB_PATH = "products.json"


def create_service(path: str | Path, on_update: OnUpdate | None = None) -> MonitorService:
    """Wire the real infrastructure into a MonitorService."""
    return MonitorService(
        repository=JsonRepository(path),
        scraper=HttpScraper(),
        notifier=create_default_notifier(),
        on_update=on_update or _print_update,
    )


def main(argv: list[str] | None = None, service: MonitorService | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        return 1

    if service is None:
        service = create_service(args.file)

    handler = _HANDLERS[args.command]
    return handler(service, args)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pricewatch", description="Flexible price monitor.")
    parser.add_argument("--file", default=DEFAULT_DB_PATH, help="path to the JSON data file")
    subparsers = parser.add_subparsers(dest="command")

    add = subparsers.add_parser("add", help="add a product to monitor")
    add.add_argument("--name", required=True)
    add.add_argument("--url", required=True)
    add.add_argument("--target-price", type=float, required=True, dest="target_price")
    add.add_argument("--selector", default=None, help="optional CSS selector for the price")

    subparsers.add_parser("list", help="list monitored products")

    remove = subparsers.add_parser("remove", help="remove a product by id")
    remove.add_argument("--id", required=True, dest="product_id")

    interval = subparsers.add_parser("set-interval", help="set the polling interval")
    interval.add_argument("--minutes", type=int, required=True)

    subparsers.add_parser("check", help="run one price check now")
    subparsers.add_parser("run", help="start continuous monitoring (Ctrl+C to stop)")

    return parser


# -- command handlers ------------------------------------------------------


def _cmd_add(service: MonitorService, args: argparse.Namespace) -> int:
    product = service.add_product(
        name=args.name,
        url=args.url,
        target_price=args.target_price,
        css_selector=args.selector,
    )
    print(f"Added '{product.name}' (id {product.id}) targeting {product.target_price}")
    return 0


def _cmd_list(service: MonitorService, args: argparse.Namespace) -> int:
    print(_format_products(service.list_products()))
    return 0


def _cmd_remove(service: MonitorService, args: argparse.Namespace) -> int:
    service.remove_product(args.product_id)
    print(f"Removed product {args.product_id}")
    return 0


def _cmd_set_interval(service: MonitorService, args: argparse.Namespace) -> int:
    service.set_poll_interval(args.minutes)
    print(f"Polling interval set to {args.minutes} minute(s)")
    return 0


def _cmd_check(service: MonitorService, args: argparse.Namespace) -> int:
    service.check_all()
    print(_format_products(service.list_products()))
    return 0


def _cmd_run(service: MonitorService, args: argparse.Namespace) -> int:
    interval = service.get_settings().poll_interval_minutes
    print(f"Monitoring {len(service.list_products())} product(s) every {interval} min. "
          "Press Ctrl+C to stop.")
    service.start()
    try:
        while service.is_running():
            service._thread.join(timeout=0.5)  # responsive to Ctrl+C
    except KeyboardInterrupt:
        print("\nStopping...")
    finally:
        service.stop()
    return 0


_HANDLERS = {
    "add": _cmd_add,
    "list": _cmd_list,
    "remove": _cmd_remove,
    "set-interval": _cmd_set_interval,
    "check": _cmd_check,
    "run": _cmd_run,
}


# -- formatting ------------------------------------------------------------


def _format_products(products: list[Product]) -> str:
    if not products:
        return "No products yet. Add one with 'add --name ... --url ... --target-price ...'."

    header = f"{'NAME':<20} {'LAST':>10} {'TARGET':>10} {'STATUS':<15} URL"
    rows = [header, "-" * len(header)]
    for p in products:
        last = "-" if p.last_price is None else f"{p.last_price:.2f}"
        rows.append(
            f"{p.name[:20]:<20} {last:>10} {p.target_price:>10.2f} "
            f"{p.status.value:<15} {p.url}  [{p.id}]"
        )
    return "\n".join(rows)


def _print_update(product: Product) -> None:
    last = "-" if product.last_price is None else f"{product.last_price:.2f}"
    print(f"[{product.status.value}] {product.name}: {last} (target {product.target_price:.2f})")


if __name__ == "__main__":  # pragma: no cover
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    raise SystemExit(main())
