#!/usr/bin/env python3
"""
cli.py — Command-Line Interface for the Binance Futures Testnet Trading Bot.

Usage examples:
    # Market BUY
    python cli.py order --symbol BTCUSDT --side BUY --type MARKET --quantity 0.01

    # Limit SELL
    python cli.py order --symbol ETHUSDT --side SELL --type LIMIT --quantity 0.1 --price 3000

    # Check account balance
    python cli.py account

    # List open orders
    python cli.py open-orders --symbol BTCUSDT
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Optional

from bot.client import BinanceClient, BinanceAPIError
from bot.logging_config import setup_logging, get_logger
from bot.orders import OrderManager
from bot.validators import validate_all, VALID_SIDES, VALID_ORDER_TYPES

# ── Logger ────────────────────────────────────────────────────────────────────
logger = get_logger("bot.cli")

# ── Colour helpers (graceful fallback when colour not supported) ──────────────
RESET = "\033[0m"
GREEN = "\033[32m"
RED = "\033[31m"
CYAN = "\033[36m"
BOLD = "\033[1m"
DIM = "\033[2m"


def _colour(text: str, code: str) -> str:
    if sys.stdout.isatty():
        return f"{code}{text}{RESET}"
    return text


def ok(msg: str) -> str:
    return _colour(msg, GREEN + BOLD)


def err(msg: str) -> str:
    return _colour(msg, RED + BOLD)


def info(msg: str) -> str:
    return _colour(msg, CYAN)


def dim(msg: str) -> str:
    return _colour(msg, DIM)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_credentials() -> tuple[str, str]:
    """
    Read API key and secret from environment variables.
    Exits with an error message if either is missing.
    """
    api_key = os.getenv("BINANCE_API_KEY", "").strip()
    api_secret = os.getenv("BINANCE_API_SECRET", "").strip()
    if not api_key or not api_secret:
        print(
            err("✗ Missing credentials."),
            "\nSet the following environment variables before running:\n"
            "  export BINANCE_API_KEY='your_testnet_api_key'\n"
            "  export BINANCE_API_SECRET='your_testnet_api_secret'\n\n"
            "  (On Windows use 'set' instead of 'export')",
        )
        sys.exit(1)
    return api_key, api_secret


def _build_client() -> BinanceClient:
    api_key, api_secret = _get_credentials()
    return BinanceClient(api_key=api_key, api_secret=api_secret)


def _print_separator(char: str = "─", width: int = 60) -> None:
    print(dim(char * width))


# ── Sub-command handlers ──────────────────────────────────────────────────────

def cmd_order(args: argparse.Namespace) -> int:
    """Handle the 'order' sub-command."""
    _print_separator()
    print(info(f"  {'BINANCE FUTURES TESTNET':^56}"))
    print(info(f"  {'ORDER PLACEMENT':^56}"))
    _print_separator()

    # ── Validate inputs ───────────────────────────────────────────────────────
    try:
        validated = validate_all(
            symbol=args.symbol,
            side=args.side,
            order_type=args.type,
            quantity=args.quantity,
            price=args.price,
            stop_price=args.stop_price,
        )
    except ValueError as exc:
        print(err(f"\n  Validation error: {exc}\n"))
        logger.error("Validation error: %s", exc)
        return 1

    # ── Print request summary ─────────────────────────────────────────────────
    print(f"\n  {BOLD}Order Request Summary{RESET}")
    _print_separator("·")
    print(f"  Symbol     : {validated['symbol']}")
    print(f"  Side       : {validated['side']}")
    print(f"  Type       : {validated['order_type']}")
    print(f"  Quantity   : {validated['quantity']}")
    if validated["price"]:
        print(f"  Price      : {validated['price']}")
    if validated["stop_price"]:
        print(f"  Stop Price : {validated['stop_price']}")
    if validated["order_type"] == "LIMIT":
        print(f"  TIF        : {args.time_in_force or 'GTC'}")
    _print_separator("·")

    logger.info(
        "CLI order command — symbol=%s side=%s type=%s qty=%s price=%s stop=%s",
        validated["symbol"],
        validated["side"],
        validated["order_type"],
        validated["quantity"],
        validated["price"],
        validated["stop_price"],
    )

    # ── Place order ───────────────────────────────────────────────────────────
    print(f"\n  Sending order to Binance Futures Testnet …\n")

    try:
        client = _build_client()
        manager = OrderManager(client)

        result = manager.place_order(
            symbol=validated["symbol"],
            side=validated["side"],
            order_type=validated["order_type"],
            quantity=validated["quantity"],
            price=validated["price"],
            stop_price=validated["stop_price"],
            time_in_force=args.time_in_force or "GTC",
        )
    except Exception as exc:
        print(err(f"  Network / unexpected error: {exc}\n"))
        logger.exception("Unexpected error in cmd_order: %s", exc)
        return 1

    # ── Print response ────────────────────────────────────────────────────────
    print(f"  {BOLD}Order Response{RESET}")
    _print_separator("·")
    print(result.summary())
    _print_separator("·")

    if result.success:
        print(f"\n  {ok('✔ SUCCESS')} — Order submitted to Binance Futures Testnet.\n")
        logger.info("Order SUCCESS — id=%s", result.order_id)
        return 0
    else:
        print(f"\n  {err('✗ FAILURE')} — Order was NOT placed.\n")
        logger.error("Order FAILURE — code=%s msg=%s", result.error_code, result.error_message)
        return 1


def cmd_account(args: argparse.Namespace) -> int:
    """Handle the 'account' sub-command."""
    print(info("\n  Fetching account information …\n"))
    try:
        client = _build_client()
        data = client.get_account()
    except BinanceAPIError as exc:
        print(err(f"  API error: {exc}\n"))
        logger.error("Account fetch failed: %s", exc)
        return 1
    except Exception as exc:
        print(err(f"  Error: {exc}\n"))
        logger.exception("Unexpected error in cmd_account: %s", exc)
        return 1

    print(f"  Total Wallet Balance : {data.get('totalWalletBalance', 'N/A')} USDT")
    print(f"  Available Balance    : {data.get('availableBalance', 'N/A')} USDT")
    print(f"  Total Unrealised PnL : {data.get('totalUnrealizedProfit', 'N/A')} USDT")
    print()

    if args.verbose:
        print(dim("  Full account response:"))
        print(dim(json.dumps(data, indent=4)))
    return 0


def cmd_open_orders(args: argparse.Namespace) -> int:
    """Handle the 'open-orders' sub-command."""
    symbol = args.symbol.strip().upper() if args.symbol else None
    print(info(f"\n  Fetching open orders{f' for {symbol}' if symbol else ''} …\n"))

    try:
        client = _build_client()
        orders = client.get_open_orders(symbol=symbol)
    except BinanceAPIError as exc:
        print(err(f"  API error: {exc}\n"))
        logger.error("open-orders fetch failed: %s", exc)
        return 1
    except Exception as exc:
        print(err(f"  Error: {exc}\n"))
        logger.exception("Unexpected error in cmd_open_orders: %s", exc)
        return 1

    if not orders:
        print("  No open orders found.\n")
        return 0

    print(f"  Found {len(orders)} open order(s):\n")
    _print_separator("·")
    for o in orders:
        print(
            f"  [{o.get('orderId')}] {o.get('symbol')}  "
            f"{o.get('side')} {o.get('type')}  "
            f"qty={o.get('origQty')}  price={o.get('price')}  "
            f"status={o.get('status')}"
        )
    _print_separator("·")
    print()
    return 0


# ── Argument parser ───────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="trading_bot",
        description=(
            "Binance Futures Testnet Trading Bot\n"
            "------------------------------------\n"
            "Place MARKET, LIMIT, and STOP_MARKET orders via the CLI.\n\n"
            "Credentials are read from environment variables:\n"
            "  BINANCE_API_KEY\n"
            "  BINANCE_API_SECRET"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Log file verbosity (default: INFO)",
    )

    subparsers = parser.add_subparsers(dest="command", metavar="<command>")
    subparsers.required = True

    # ── 'order' sub-command ───────────────────────────────────────────────────
    order_parser = subparsers.add_parser(
        "order",
        help="Place a new futures order",
        description="Place a MARKET, LIMIT, or STOP_MARKET order on Binance Futures Testnet.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python cli.py order --symbol BTCUSDT --side BUY --type MARKET --quantity 0.01\n"
            "  python cli.py order --symbol ETHUSDT --side SELL --type LIMIT "
            "--quantity 0.1 --price 3000\n"
            "  python cli.py order --symbol BTCUSDT --side BUY --type STOP_MARKET "
            "--quantity 0.01 --stop-price 65000\n"
        ),
    )
    order_parser.add_argument(
        "--symbol", "-s", required=True,
        help="Trading pair symbol (e.g. BTCUSDT, ETHUSDT)"
    )
    order_parser.add_argument(
        "--side", "-d", required=True,
        choices=sorted(VALID_SIDES),
        help="Order side: BUY or SELL"
    )
    order_parser.add_argument(
        "--type", "-t", required=True,
        choices=sorted(VALID_ORDER_TYPES),
        metavar="ORDER_TYPE",
        help=f"Order type: {' | '.join(sorted(VALID_ORDER_TYPES))}"
    )
    order_parser.add_argument(
        "--quantity", "-q", required=True, type=float,
        help="Order quantity (e.g. 0.01 for 0.01 BTC)"
    )
    order_parser.add_argument(
        "--price", "-p", type=float, default=None,
        help="Limit price — required for LIMIT orders"
    )
    order_parser.add_argument(
        "--stop-price", type=float, default=None, dest="stop_price",
        help="Stop trigger price — required for STOP_MARKET orders"
    )
    order_parser.add_argument(
        "--time-in-force", "-f", default="GTC",
        choices=["GTC", "IOC", "FOK"],
        help="Time-in-force for LIMIT orders (default: GTC)"
    )
    order_parser.set_defaults(func=cmd_order)

    # ── 'account' sub-command ─────────────────────────────────────────────────
    account_parser = subparsers.add_parser(
        "account",
        help="Show futures account balance",
    )
    account_parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Print full account JSON response"
    )
    account_parser.set_defaults(func=cmd_account)

    # ── 'open-orders' sub-command ─────────────────────────────────────────────
    oo_parser = subparsers.add_parser(
        "open-orders",
        help="List open orders",
    )
    oo_parser.add_argument(
        "--symbol", "-s", default=None,
        help="Filter by symbol (e.g. BTCUSDT). Omit for all symbols."
    )
    oo_parser.set_defaults(func=cmd_open_orders)

    return parser


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    setup_logging(log_level=args.log_level)
    logger.info("Trading bot started — command=%s", args.command)

    try:
        exit_code = args.func(args)
    except KeyboardInterrupt:
        print("\n  Interrupted by user.\n")
        logger.warning("Interrupted by user.")
        sys.exit(130)

    sys.exit(exit_code or 0)


if __name__ == "__main__":
    main()
