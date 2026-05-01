"""
Low-level Binance Futures Testnet REST client.

Handles:
  - HMAC-SHA256 request signing
  - Timestamp synchronisation
  - HTTP request / response lifecycle
  - Structured logging of every outgoing request and incoming response
  - Translation of Binance error payloads into Python exceptions
"""

from __future__ import annotations

import hashlib
import hmac
import time
from typing import Any, Dict, Optional
from urllib.parse import urlencode

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from bot.logging_config import get_logger

logger = get_logger("bot.client")

# ── Constants ─────────────────────────────────────────────────────────────────
TESTNET_BASE_URL = "https://testnet.binancefuture.com"
DEFAULT_TIMEOUT = 10  # seconds
RECV_WINDOW = 5_000   # ms; tolerance for timestamp drift

# Retry on transient network errors (not on 4xx/5xx — those need to propagate)
_RETRY_CONFIG = Retry(
    total=3,
    backoff_factor=0.5,
    status_forcelist=[500, 502, 503, 504],
    allowed_methods=["GET", "POST", "DELETE"],
    raise_on_status=False,
)


class BinanceAPIError(Exception):
    """Raised when Binance returns a non-2xx HTTP status or error payload."""

    def __init__(self, code: int, message: str, http_status: int = 0):
        self.code = code
        self.message = message
        self.http_status = http_status
        super().__init__(f"[HTTP {http_status}] Binance error {code}: {message}")


class BinanceClient:
    """
    Thin wrapper around the Binance Futures REST API.

    Args:
        api_key:    Binance API key.
        api_secret: Binance API secret.
        base_url:   Base URL (defaults to Testnet).
        timeout:    Per-request timeout in seconds.
    """

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        base_url: str = TESTNET_BASE_URL,
        timeout: int = DEFAULT_TIMEOUT,
    ) -> None:
        if not api_key or not api_secret:
            raise ValueError("api_key and api_secret must not be empty.")
        self._api_key = api_key
        self._api_secret = api_secret.encode()
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._session = self._build_session()
        logger.info("BinanceClient initialised — base_url=%s", self.base_url)

    # ── Session setup ─────────────────────────────────────────────────────────

    def _build_session(self) -> requests.Session:
        session = requests.Session()
        session.headers.update(
            {
                "X-MBX-APIKEY": self._api_key,
                "Content-Type": "application/x-www-form-urlencoded",
            }
        )
        adapter = HTTPAdapter(max_retries=_RETRY_CONFIG)
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        return session

    # ── Signing ───────────────────────────────────────────────────────────────

    def _sign(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Add timestamp + HMAC-SHA256 signature to *params* (mutates & returns)."""
        params["timestamp"] = int(time.time() * 1000)
        params["recvWindow"] = RECV_WINDOW
        query_string = urlencode(params)
        signature = hmac.new(
            self._api_secret, query_string.encode(), hashlib.sha256
        ).hexdigest()
        params["signature"] = signature
        return params

    # ── HTTP helpers ──────────────────────────────────────────────────────────

    def _request(
        self,
        method: str,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        signed: bool = False,
    ) -> Any:
        """
        Execute an HTTP request and return the parsed JSON body.

        Args:
            method: HTTP verb (GET / POST / DELETE).
            path:   API endpoint path (e.g. '/fapi/v1/order').
            params: Query / body parameters.
            signed: Whether to add timestamp + signature.

        Returns:
            Parsed JSON response.

        Raises:
            BinanceAPIError: On API-level errors.
            requests.RequestException: On network-level errors.
        """
        params = dict(params or {})
        if signed:
            params = self._sign(params)

        url = f"{self.base_url}{path}"

        # Log request (mask secret-adjacent fields)
        safe_params = {k: v for k, v in params.items() if k != "signature"}
        logger.info("→ %s %s  params=%s", method.upper(), url, safe_params)

        try:
            if method.upper() in ("GET", "DELETE"):
                response = self._session.request(
                    method, url, params=params, timeout=self.timeout
                )
            else:
                response = self._session.request(
                    method, url, data=params, timeout=self.timeout
                )
        except requests.exceptions.Timeout as exc:
            logger.error("Request timed out: %s %s — %s", method, url, exc)
            raise
        except requests.exceptions.ConnectionError as exc:
            logger.error("Connection error: %s %s — %s", method, url, exc)
            raise
        except requests.exceptions.RequestException as exc:
            logger.error("Unexpected request error: %s %s — %s", method, url, exc)
            raise

        logger.info(
            "← HTTP %s  %s  body=%s",
            response.status_code,
            url,
            response.text[:500],  # truncate huge responses
        )

        return self._handle_response(response)

    @staticmethod
    def _handle_response(response: requests.Response) -> Any:
        """Parse JSON and surface Binance error codes as BinanceAPIError."""
        try:
            data = response.json()
        except ValueError:
            response.raise_for_status()
            return response.text

        if isinstance(data, dict) and "code" in data and data["code"] != 200:
            # Binance error format: {"code": -XXXX, "msg": "..."}
            raise BinanceAPIError(
                code=data.get("code", 0),
                message=data.get("msg", "Unknown error"),
                http_status=response.status_code,
            )

        if response.status_code >= 400:
            raise BinanceAPIError(
                code=response.status_code,
                message=str(data),
                http_status=response.status_code,
            )

        return data

    # ── Public API methods ────────────────────────────────────────────────────

    def get_server_time(self) -> int:
        """Return Binance server time in milliseconds."""
        data = self._request("GET", "/fapi/v1/time")
        return data["serverTime"]

    def get_exchange_info(self, symbol: Optional[str] = None) -> Dict:
        """Fetch exchange info (optionally filtered to one symbol)."""
        params = {}
        if symbol:
            params["symbol"] = symbol
        return self._request("GET", "/fapi/v1/exchangeInfo", params=params)

    def get_account(self) -> Dict:
        """Fetch futures account details (signed)."""
        return self._request("GET", "/fapi/v2/account", signed=True)

    def place_order(self, **order_params) -> Dict:
        """
        Place a new futures order.

        Keyword args mirror the Binance /fapi/v1/order POST parameters:
            symbol, side, type, quantity, price, timeInForce, stopPrice, etc.

        Returns:
            Raw Binance order response dict.
        """
        return self._request(
            "POST", "/fapi/v1/order", params=order_params, signed=True
        )

    def get_order(self, symbol: str, order_id: int) -> Dict:
        """Query a specific order by its ID."""
        return self._request(
            "GET",
            "/fapi/v1/order",
            params={"symbol": symbol, "orderId": order_id},
            signed=True,
        )

    def cancel_order(self, symbol: str, order_id: int) -> Dict:
        """Cancel an open order."""
        return self._request(
            "DELETE",
            "/fapi/v1/order",
            params={"symbol": symbol, "orderId": order_id},
            signed=True,
        )

    def get_open_orders(self, symbol: Optional[str] = None) -> list:
        """List all open orders, optionally filtered by symbol."""
        params = {}
        if symbol:
            params["symbol"] = symbol
        return self._request("GET", "/fapi/v1/openOrders", params=params, signed=True)
