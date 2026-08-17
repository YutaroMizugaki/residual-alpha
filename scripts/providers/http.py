"""HTTP helpers. HTML challenge pages are fetch failures."""

from __future__ import annotations

import json
from typing import Callable
from urllib.parse import quote
from urllib.request import Request, urlopen

from providers.errors import BotWallError, FetchError

Fetcher = Callable[[str], tuple[int, str, str]]

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 residual-alpha free-data-provider",
    "Accept": "application/json,text/csv,text/plain;q=0.9,*/*;q=0.8",
}


def default_fetcher(url: str) -> tuple[int, str, str]:
    request = Request(url, headers=DEFAULT_HEADERS)
    try:
        with urlopen(request, timeout=20) as response:
            status = int(getattr(response, "status", 200))
            content_type = str(response.headers.get("Content-Type") or "")
            body = response.read().decode("utf-8", errors="replace")
            return status, content_type, body
    except FetchError:
        raise
    except Exception as exc:  # noqa: BLE001 — network failures become FetchError
        raise FetchError(f"request failed: {url}") from exc


def reject_html(body: str, content_type: str) -> None:
    ctype = content_type.lower()
    text = body.lstrip()
    if "text/html" in ctype or text.startswith("<!DOCTYPE") or text.startswith("<html"):
        raise BotWallError("provider returned HTML instead of market data")


def yahoo_chart_url(symbol: str, range_: str = "1y") -> str:
    return (
        "https://query1.finance.yahoo.com/v8/finance/chart/"
        f"{quote(symbol, safe='')}?interval=1d&range={range_}"
    )


def fetch_yahoo_chart_json(
    symbol: str,
    *,
    range_: str = "1y",
    fetcher: Fetcher | None = None,
) -> dict:
    fetch = fetcher or default_fetcher
    status, content_type, body = fetch(yahoo_chart_url(symbol, range_))
    if status != 200:
        raise FetchError(f"Yahoo chart HTTP {status} for {symbol}")
    reject_html(body, content_type)
    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        raise FetchError(f"Yahoo chart JSON decode failed for {symbol}") from exc
    return payload


def cache_filename(symbol: str) -> str:
    return symbol.replace("^", "_") + ".json"
