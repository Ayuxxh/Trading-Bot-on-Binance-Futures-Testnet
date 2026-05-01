"""
Input validation for order parameters.
All functions raise ValueError with a human-readable message on failure.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Optional

from bot.logging_config import get_logger

logger = get_logger("bot.validators")

# ── Allowed values ────────────────────────────────────────────────────────────
VALID_SIDES = {"BUY", "SELL"}
VALID_ORDER_TYPES = {"MARKET", "LIMIT", "STOP_MARKET"}

# Binance symbol rules: 1-20 uppercase alphanum chars
_MAX_SYMBOL_LEN = 20
_MIN_QTY = Decimal("0.001")
_MIN_PRICE = Decimal("0.01")


# ── Public validators ─────────────────────────────────────────────────────────

def validate_symbol(symbol: str) -> str:
    """Normalise and validate a trading symbol (e.g. BTCUSDT)."""
    symbol = symbol.strip().upper()
    if not symbol:
        raise ValueError("Symbol cannot be empty.")
    if not symbol.isalnum():
        raise ValueError(
            f"Symbol '{symbol}' contains invalid characters. "
            "Only letters and digits are allowed (e.g. BTCUSDT)."
        )
    if len(symbol) > _MAX_SYMBOL_LEN:
        raise ValueError(
            f"Symbol '{symbol}' is too long (max {_MAX_SYMBOL_LEN} chars)."
        )
    logger.debug("Symbol validated: %s", symbol)
    return symbol


def validate_side(side: str) -> str:
    """Validate order side: BUY or SELL."""
    side = side.strip().upper()
    if side not in VALID_SIDES:
        raise ValueError(
            f"Invalid side '{side}'. Must be one of: {', '.join(sorted(VALID_SIDES))}."
        )
    logger.debug("Side validated: %s", side)
    return side


def validate_order_type(order_type: str) -> str:
    """Validate order type: MARKET, LIMIT, or STOP_MARKET."""
    order_type = order_type.strip().upper()
    if order_type not in VALID_ORDER_TYPES:
        raise ValueError(
            f"Invalid order type '{order_type}'. "
            f"Must be one of: {', '.join(sorted(VALID_ORDER_TYPES))}."
        )
    logger.debug("Order type validated: %s", order_type)
    return order_type


def validate_quantity(quantity: str | float) -> Decimal:
    """Parse and validate quantity (must be positive)."""
    try:
        qty = Decimal(str(quantity))
    except InvalidOperation:
        raise ValueError(f"Quantity '{quantity}' is not a valid number.")
    if qty <= 0:
        raise ValueError(f"Quantity must be greater than 0 (got {qty}).")
    if qty < _MIN_QTY:
        raise ValueError(
            f"Quantity {qty} is below the minimum allowed ({_MIN_QTY})."
        )
    logger.debug("Quantity validated: %s", qty)
    return qty


def validate_price(price: Optional[str | float], order_type: str) -> Optional[Decimal]:
    """
    Validate price field.

    - For LIMIT / STOP_MARKET orders: required and must be positive.
    - For MARKET orders: must be None / empty.
    """
    order_type = order_type.strip().upper()

    if order_type == "MARKET":
        if price is not None and str(price).strip() != "":
            logger.warning(
                "Price '%s' was supplied for a MARKET order and will be ignored.", price
            )
        return None

    # LIMIT or STOP_MARKET — price is mandatory
    if price is None or str(price).strip() == "":
        raise ValueError(
            f"Price is required for {order_type} orders. "
            "Please provide a --price value."
        )
    try:
        p = Decimal(str(price))
    except InvalidOperation:
        raise ValueError(f"Price '{price}' is not a valid number.")
    if p <= 0:
        raise ValueError(f"Price must be greater than 0 (got {p}).")
    if p < _MIN_PRICE:
        raise ValueError(
            f"Price {p} is below the minimum allowed ({_MIN_PRICE})."
        )
    logger.debug("Price validated: %s", p)
    return p


def validate_stop_price(
    stop_price: Optional[str | float], order_type: str
) -> Optional[Decimal]:
    """
    Validate stop price for STOP_MARKET orders.
    Required when order_type == STOP_MARKET.
    """
    order_type = order_type.strip().upper()
    if order_type != "STOP_MARKET":
        return None

    if stop_price is None or str(stop_price).strip() == "":
        raise ValueError(
            "Stop price (--stop-price) is required for STOP_MARKET orders."
        )
    try:
        sp = Decimal(str(stop_price))
    except InvalidOperation:
        raise ValueError(f"Stop price '{stop_price}' is not a valid number.")
    if sp <= 0:
        raise ValueError(f"Stop price must be greater than 0 (got {sp}).")
    logger.debug("Stop price validated: %s", sp)
    return sp


def validate_all(
    symbol: str,
    side: str,
    order_type: str,
    quantity: str | float,
    price: Optional[str | float] = None,
    stop_price: Optional[str | float] = None,
) -> dict:
    """
    Run all validators and return a clean, typed params dict.

    Returns:
        {
            "symbol": str,
            "side": str,
            "order_type": str,
            "quantity": Decimal,
            "price": Decimal | None,
            "stop_price": Decimal | None,
        }
    """
    logger.info(
        "Validating order params — symbol=%s side=%s type=%s qty=%s price=%s stop_price=%s",
        symbol, side, order_type, quantity, price, stop_price,
    )
    validated = {
        "symbol": validate_symbol(symbol),
        "side": validate_side(side),
        "order_type": validate_order_type(order_type),
        "quantity": validate_quantity(quantity),
        "price": validate_price(price, order_type),
        "stop_price": validate_stop_price(stop_price, order_type),
    }
    logger.info("Validation passed: %s", validated)
    return validated
