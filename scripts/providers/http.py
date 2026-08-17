"""HTTP helpers. HTML challenge pages are fetch failures. Keys are never logged."""

from __future__ import annotations

import json
import os
import re
from datetime import date, timedelta
from typing import Callable
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from providers.errors import BotWallError, FetchError

Fetcher = Callable[[str], tuple[int, str, str]]
BinaryFetcher = Callable[[str], tuple[int, str, bytes]]

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 residual-alpha free-data-provider",
    "Accept": "application/json,text/csv,text/plain;q=0.9,*/*;q=0.8",
}

JQUANTS_SUMMARY_URL = "https://api.jquants.com/v2/fins/summary"
JQUANTS_BARS_URL = "https://api.jquants.com/v2/equities/bars/daily"
EDINET_DOCUMENTS_URL = "https://api.edinet-fsa.go.jp/api/v2/documents.json"
EDINET_DOCUMENT_BASE = "https://api.edinet-fsa.go.jp/api/v2/documents"


def redact_url(url: str) -> str:
    redacted = re.sub(r"(Subscription-Key=)[^&]+", r"\1REDACTED", url, flags=re.IGNORECASE)
    return redacted


def default_fetcher(url: str, extra_headers: dict[str, str] | None = None) -> tuple[int, str, str]:
    request = Request(url, headers={**DEFAULT_HEADERS, **(extra_headers or {})})
    try:
        with urlopen(request, timeout=20) as response:
            status = int(getattr(response, "status", 200))
            content_type = str(response.headers.get("Content-Type") or "")
            body = response.read().decode("utf-8", errors="replace")
            return status, content_type, body
    except FetchError:
        raise
    except Exception as exc:  # noqa: BLE001 — network failures become FetchError
        raise FetchError(f"request failed: {redact_url(url)}") from exc


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


FUNDAMENTALS_TYPES = ",".join(
    [
        "annualStockholdersEquity",
        "annualNetIncomeCommonStockholders",
        "annualOrdinarySharesNumber",
    ]
)
# Wide window so newly reported fiscal years are included without a code change.
YAHOO_FUNDAMENTALS_PERIOD1 = 1483228800  # 2017-01-01 UTC
YAHOO_FUNDAMENTALS_PERIOD2 = 1893456000  # 2030-01-01 UTC


def yahoo_fundamentals_url(
    symbol: str,
    *,
    period1: int = YAHOO_FUNDAMENTALS_PERIOD1,
    period2: int = YAHOO_FUNDAMENTALS_PERIOD2,
) -> str:
    query = urlencode(
        {
            "symbol": symbol,
            "type": FUNDAMENTALS_TYPES,
            "period1": str(period1),
            "period2": str(period2),
        }
    )
    return (
        "https://query1.finance.yahoo.com/ws/fundamentals-timeseries/v1/finance/timeseries/"
        f"{quote(symbol, safe='')}?{query}"
    )


def fetch_yahoo_fundamentals_json(
    symbol: str,
    *,
    fetcher: Fetcher | None = None,
) -> dict:
    fetch = fetcher or default_fetcher
    status, content_type, body = fetch(yahoo_fundamentals_url(symbol))
    if status != 200:
        raise FetchError(f"Yahoo fundamentals HTTP {status} for {symbol}")
    reject_html(body, content_type)
    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        raise FetchError(f"Yahoo fundamentals JSON decode failed for {symbol}") from exc
    return payload


def cache_filename(symbol: str) -> str:
    return symbol.replace("^", "_") + ".json"


def _parse_json_body(body: str, *, label: str) -> dict:
    reject_html(body, "application/json")
    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        raise FetchError(f"{label} JSON decode failed") from exc
    if not isinstance(payload, dict):
        raise FetchError(f"{label} JSON is not an object")
    return payload


def jquants_summary_url(code: str, *, pagination_key: str | None = None) -> str:
    query = {"code": code}
    if pagination_key:
        query["pagination_key"] = pagination_key
    return f"{JQUANTS_SUMMARY_URL}?{urlencode(query)}"


def fetch_jquants_summary_json(
    code: str,
    *,
    api_key: str | None = None,
    fetcher: Fetcher | None = None,
) -> dict:
    """
    Live calls need JQUANTS_API_KEY (x-api-key). Injected fetchers skip the key
    so CI can use recorded payloads.
    """
    rows: list[object] = []
    pagination_key: str | None = None
    key = api_key if api_key is not None else os.environ.get("JQUANTS_API_KEY")
    extra = {"x-api-key": key, "Accept": "application/json"} if fetcher is None else None
    if fetcher is None and not key:
        raise FetchError("JQUANTS_API_KEY is not set")

    for _ in range(20):
        url = jquants_summary_url(code, pagination_key=pagination_key)
        if fetcher is None:
            status, content_type, body = default_fetcher(url, extra_headers=extra)
        else:
            status, content_type, body = fetcher(url)
        if status in (401, 403):
            raise FetchError(f"J-Quants HTTP {status} for {code}")
        if status != 200:
            raise FetchError(f"J-Quants HTTP {status} for {code}")
        reject_html(body, content_type)
        payload = _parse_json_body(body, label=f"J-Quants summary {code}")
        data = payload.get("data")
        if not isinstance(data, list):
            raise FetchError(f"J-Quants summary data missing for {code}")
        rows.extend(data)
        pagination_key = payload.get("pagination_key")
        if not pagination_key:
            return {"data": rows}
    raise FetchError(f"J-Quants summary pagination exceeded for {code}")


def jquants_bars_window(range_: str = "1y") -> tuple[str, str]:
    days = {"1y": 400, "2y": 800, "5y": 1900}.get(range_, 400)
    end = date.today()
    start = end - timedelta(days=days)
    return start.isoformat(), end.isoformat()


def jquants_bars_url(
    code: str,
    *,
    from_: str | None = None,
    to: str | None = None,
    pagination_key: str | None = None,
) -> str:
    query = {"code": code}
    if from_:
        query["from"] = from_
    if to:
        query["to"] = to
    if pagination_key:
        query["pagination_key"] = pagination_key
    return f"{JQUANTS_BARS_URL}?{urlencode(query)}"


def fetch_jquants_bars_json(
    code: str,
    *,
    from_: str | None = None,
    to: str | None = None,
    api_key: str | None = None,
    fetcher: Fetcher | None = None,
) -> dict:
    """
    Live calls need JQUANTS_API_KEY (x-api-key). Injected fetchers skip the key
    so CI can use recorded payloads.
    """
    rows: list[object] = []
    pagination_key: str | None = None
    key = api_key if api_key is not None else os.environ.get("JQUANTS_API_KEY")
    extra = {"x-api-key": key, "Accept": "application/json"} if fetcher is None else None
    if fetcher is None and not key:
        raise FetchError("JQUANTS_API_KEY is not set")

    for _ in range(20):
        url = jquants_bars_url(code, from_=from_, to=to, pagination_key=pagination_key)
        if fetcher is None:
            status, content_type, body = default_fetcher(url, extra_headers=extra)
        else:
            status, content_type, body = fetcher(url)
        if status in (401, 403):
            raise FetchError(f"J-Quants HTTP {status} for {code}")
        if status != 200:
            raise FetchError(f"J-Quants HTTP {status} for {code}")
        reject_html(body, content_type)
        payload = _parse_json_body(body, label=f"J-Quants bars {code}")
        data = payload.get("data")
        if not isinstance(data, list):
            raise FetchError(f"J-Quants bars data missing for {code}")
        rows.extend(data)
        pagination_key = payload.get("pagination_key")
        if not pagination_key:
            return {"data": rows}
    raise FetchError(f"J-Quants bars pagination exceeded for {code}")


def edinet_documents_url(date: str, *, api_key: str | None = None) -> str:
    query = {"date": date, "type": "2"}
    if api_key:
        query["Subscription-Key"] = api_key
    return f"{EDINET_DOCUMENTS_URL}?{urlencode(query)}"


def fetch_edinet_documents_json(
    date: str,
    *,
    api_key: str | None = None,
    fetcher: Fetcher | None = None,
) -> dict:
    """
    Live calls need EDINET_API_KEY. Injected fetchers skip the key so CI
    can use recorded payloads. This helper does not download XBRL zips.
    """
    if fetcher is None:
        key = api_key if api_key is not None else os.environ.get("EDINET_API_KEY")
        if not key:
            raise FetchError("EDINET_API_KEY is not set")
        url = edinet_documents_url(date, api_key=key)
        status, content_type, body = default_fetcher(url)
    else:
        url = edinet_documents_url(date)
        status, content_type, body = fetcher(url)
    if status in (401, 403):
        raise FetchError(f"EDINET HTTP {status}")
    if status != 200:
        raise FetchError(f"EDINET HTTP {status}")
    reject_html(body, content_type)
    return _parse_json_body(body, label="EDINET documents")


def default_binary_fetcher(url: str) -> tuple[int, str, bytes]:
    request = Request(url, headers=DEFAULT_HEADERS)
    try:
        with urlopen(request, timeout=60) as response:
            status = int(getattr(response, "status", 200))
            content_type = str(response.headers.get("Content-Type") or "")
            body = response.read()
            return status, content_type, body
    except FetchError:
        raise
    except Exception as exc:  # noqa: BLE001 — network failures become FetchError
        raise FetchError(f"request failed: {redact_url(url)}") from exc


def edinet_xbrl_url(doc_id: str, *, api_key: str | None = None) -> str:
    query = {"type": "1"}
    if api_key:
        query["Subscription-Key"] = api_key
    return f"{EDINET_DOCUMENT_BASE}/{quote(doc_id)}?{urlencode(query)}"


def _looks_like_html_bytes(data: bytes) -> bool:
    sniff = data.lstrip()[:80].lower()
    return sniff.startswith(b"<!doctype") or sniff.startswith(b"<html")


def fetch_edinet_xbrl_zip(
    doc_id: str,
    *,
    api_key: str | None = None,
    fetcher: BinaryFetcher | None = None,
) -> bytes:
    """Download yuho XBRL zip (type=1). Live calls need EDINET_API_KEY."""
    if fetcher is None:
        key = api_key if api_key is not None else os.environ.get("EDINET_API_KEY")
        if not key:
            raise FetchError("EDINET_API_KEY is not set")
        url = edinet_xbrl_url(doc_id, api_key=key)
        status, content_type, body = default_binary_fetcher(url)
    else:
        url = edinet_xbrl_url(doc_id)
        status, content_type, body = fetcher(url)
    if status in (401, 403):
        raise FetchError(f"EDINET HTTP {status}")
    if status != 200:
        raise FetchError(f"EDINET HTTP {status}")
    if "text/html" in content_type.lower() or _looks_like_html_bytes(body):
        raise BotWallError("EDINET XBRL returned HTML instead of a zip")
    return body
