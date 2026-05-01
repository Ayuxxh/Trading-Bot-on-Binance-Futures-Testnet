"""
Order placement logic for Binance Futures Testnet.

Translates validated user parameters into Binance API calls and returns
a normalised OrderResult object for uniform display / downstream use.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Dict, Optional

from bot.client import BinanceClient, BinanceAPIError
from bot.logging_config import get_logger

logger = get_logger("bot.orders")


# ── Result dataclass ──────────────────────────────────────────────────────────

@dataclass
class OrderResult:
    """Normalised view of a Binance order response."""

    success: bool
    order_id: Optional[int] = None
    client_order_id: Optional[str] = None
    symbol: Optional[str] = None
    side: Optional[str] = None
    order_type: Optional[str] = None
    status: Optional[str] = None
    price: Optional[str] = None
    avg_price: Optional[str] = None
    orig_qty: Optional[str] = None
    executed_qty: Optional[str] = None
    time_in_force: Optional[str] = None
    raw_response: Dict[str, Any] = field(default_factory=dict)
    error_code: Optional[int] = None
    error_message: Optional[str] = None

    # ── Constructors ──────────────────────────────────────────────────────────

    @classmethod
    def from_response(cls, data: Dict[str, Any]) -> "OrderResult":
        return cls(
            success=True,
            order_id=data.get("orderId"),
            client_order_id=data.get("clientOrderId"),
            symbol=data.get("symbol"),
            side=data.get("side"),
            order_type=data.get("type"),
            status=data.get("status"),
            price=data.get("price"),
            avg_price=data.get("avgPrice"),
            orig_qty=data.get("origQty"),
            executed_qty=data.get("executedQty"),
            time_in_force=data.get("timeInForce"),
            raw_response=data,
        )

    @classmethod
    def from_error(
        cls, error_code: int, error_message: str, raw: Optional[Dict] = None
    ) -> "OrderResult":
        return cls(
            success=False,
            error_code=error_code,
            error_message=error_message,
            raw_response=raw or {},
        )

    # ── Display ───────────────────────────────────────────────────────────────

    def summary(self) -> str:
        """Return a human-readable multi-line summary."""
        if not self.success:
            return (
                f"  ✗ Order FAILED\n"
                f"  Error code   : {self.error_code}\n"
                f"  Error message: {self.error_message}"
            )
        lines = [
            "  ✔ Order placed successfully",
            f"  Order ID      : {self.order_id}",
            f"  Client OID    : {self.client_order_id}",
            f"  Symbol        : {self.symbol}",
            f"  Side          : {self.side}",
            f"  Type          : {self.order_type}",
            f"  Status        : {self.status}",
        ]
        if self.price and self.price != "0" and self.price != "0.00000":
            lines.append(f"  Price         : {self.price}")
        if self.avg_price and self.avg_price not in ("0", "0.00000", ""):
            lines.append(f"  Avg Price     : {self.avg_price}")
        lines += [
            f"  Orig Qty      : {self.orig_qty}",
            f"  Executed Qty  : {self.executed_qty}",
        ]
        if self.time_in_force:
            lines.append(f"  Time-in-Force : {self.time_in_force}")
        return "\n".join(lines)


# ── Order builder ─────────────────────────────────────────────────────────────

class OrderManager:
    """
    High-level order operations built on top of BinanceClient.

    Args:
        client: An initialised BinanceClient instance.
    """

    def __init__(self, client: BinanceClient) -> None:
        self._client = client

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _log_request_summary(self, params: Dict[str, Any]) -> None:
        logger.info("Order request summary: %s", json.dumps(params, default=str))

    def _log_response_summary(self, result: OrderResult) -> None:
        if result.success:
            logger.info(
                "Order response — id=%s status=%s execQty=%s avgPrice=%s",
                result.order_id,
                result.status,
                result.executed_qty,
                result.avg_price,
            )
        else:
            logger.error(
                "Order failed — code=%s msg=%s",
                result.error_code,
                result.error_message,
            )

    # ── Market order ──────────────────────────────────────────────────────────

    def place_market_order(
        self,
        symbol: str,
        side: str,
        quantity: Decimal,
    ) -> OrderResult:
        """
        Place a MARKET order.

        Args:
            symbol:   e.g. "BTCUSDT"
            side:     "BUY" or "SELL"
            quantity: Order quantity.

        Returns:
            OrderResult
        """
        params: Dict[str, Any] = {
            "symbol": symbol,
            "side": side,
            "type": "MARKET",
            "quantity": str(quantity),
        }
        self._log_request_summary(params)

        try:
            response = self._client.place_order(**params)
            result = OrderResult.from_response(response)
        except BinanceAPIError as exc:
            logger.error("BinanceAPIError placing MARKET order: %s", exc)
            result = OrderResult.from_error(exc.code, exc.message)
        except Exception as exc:
            logger.exception("Unexpected error placing MARKET order: %s", exc)
            result = OrderResult.from_error(-1, str(exc))

        self._log_response_summary(result)
        return result

    # ── Limit order ───────────────────────────────────────────────────────────

    def place_limit_order(
        self,
        symbol: str,
        side: str,
        quantity: Decimal,
        price: Decimal,
        time_in_force: str = "GTC",
    ) -> OrderResult:
        """
        Place a LIMIT order.

        Args:
            symbol:        e.g. "BTCUSDT"
            side:          "BUY" or "SELL"
            quantity:      Order quantity.
            price:         Limit price.
            time_in_force: GTC | IOC | FOK (default GTC).

        Returns:
            OrderResult
        """
        params: Dict[str, Any] = {
            "symbol": symbol,
            "side": side,
            "type": "LIMIT",
            "quantity": str(quantity),
            "price": str(price),
            "timeInForce": time_in_force,
        }
        self._log_request_summary(params)

        try:
            response = self._client.place_order(**params)
            result = OrderResult.from_response(response)
        except BinanceAPIError as exc:
            logger.error("BinanceAPIError placing LIMIT order: %s", exc)
            result = OrderResult.from_error(exc.code, exc.message)
        except Exception as exc:
            logger.exception("Unexpected error placing LIMIT order: %s", exc)
            result = OrderResult.from_error(-1, str(exc))

        self._log_response_summary(result)
        return result

    # ── Stop-Market order (bonus) ─────────────────────────────────────────────

    def place_stop_market_order(
        self,
        symbol: str,
        side: str,
        quantity: Decimal,
        stop_price: Decimal,
    ) -> OrderResult:
        """
        Place a STOP_MARKET order (closes position when price hits stop_price).

        Args:
            symbol:     e.g. "BTCUSDT"
            side:       "BUY" or "SELL"
            quantity:   Order quantity.
            stop_price: Trigger price.

        Returns:
            OrderResult
        """
        params: Dict[str, Any] = {
            "symbol": symbol,
            "side": side,
            "type": "STOP_MARKET",
            "quantity": str(quantity),
            "stopPrice": str(stop_price),
        }
        self._log_request_summary(params)

        try:
            response = self._client.place_order(**params)
            result = OrderResult.from_response(response)
        except BinanceAPIError as exc:
            logger.error("BinanceAPIError placing STOP_MARKET order: %s", exc)
            result = OrderResult.from_error(exc.code, exc.message)
        except Exception as exc:
            logger.exception("Unexpected error placing STOP_MARKET order: %s", exc)
            result = OrderResult.from_error(-1, str(exc))

        self._log_response_summary(result)
        return result

    # ── Dispatcher ────────────────────────────────────────────────────────────

    def place_order(
        self,
        symbol: str,
        side: str,
        order_type: str,
        quantity: Decimal,
        price: Optional[Decimal] = None,
        stop_price: Optional[Decimal] = None,
        time_in_force: str = "GTC",
    ) -> OrderResult:
        """
        Unified order entry-point — dispatches to the correct method by type.

        Args:
            symbol:        Trading pair (e.g. BTCUSDT).
            side:          BUY or SELL.
            order_type:    MARKET | LIMIT | STOP_MARKET.
            quantity:      Order size.
            price:         Required for LIMIT.
            stop_price:    Required for STOP_MARKET.
            time_in_force: GTC | IOC | FOK (LIMIT only).

        Returns:
            OrderResult
        """
        if order_type == "MARKET":
            return self.place_market_order(symbol, side, quantity)
        elif order_type == "LIMIT":
            if price is None:
                raise ValueError("price is required for LIMIT orders.")
            return self.place_limit_order(symbol, side, quantity, price, time_in_force)
        elif order_type == "STOP_MARKET":
            if stop_price is None:
                raise ValueError("stop_price is required for STOP_MARKET orders.")
            return self.place_stop_market_order(symbol, side, quantity, stop_price)
        else:
            raise ValueError(f"Unsupported order type: {order_type}")
