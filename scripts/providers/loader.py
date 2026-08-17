"""Load engine-ready snapshots. Fixture remains the default deterministic source."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from providers.edinet_xbrl import parse_edinet_xbrl_dir
from providers.errors import FetchError, ProviderError
from providers.http import (
    cache_filename,
    fetch_jquants_bars_json,
    fetch_jquants_summary_json,
    fetch_yahoo_chart_json,
    fetch_yahoo_fundamentals_json,
    jquants_bars_window,
)
from providers.jquants_bars import parse_jquants_bars
from providers.jquants_summary import parse_jquants_summary
from providers.series import aligned_simple_returns
from providers.stooq_csv import parse_stooq_csv
from providers.yahoo_chart import parse_yahoo_chart
from providers.yahoo_fundamentals import parse_yahoo_fundamentals

ROOT = Path(__file__).resolve().parents[2]
FIXTURE_PATH = ROOT / "scripts" / "fixtures" / "stocks.json"
UNIVERSE_PATH = ROOT / "scripts" / "providers" / "universe.json"
FUNDAMENTALS_PATH = ROOT / "scripts" / "providers" / "fundamentals.json"


@dataclass(frozen=True)
class DataSnapshot:
    source: str
    source_label: str
    price_source: str
    fundamentals_source: str
    market_symbol: str | None
    as_of_date: str | None
    disclaimer_ja: str
    disclaimer_en: str
    assumptions: dict[str, Any]
    stocks: list[dict[str, Any]]

    def meta(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "sourceLabel": self.source_label,
            "priceSource": self.price_source,
            "fundamentalsSource": self.fundamentals_source,
            "marketSymbol": self.market_symbol,
            "asOfDate": self.as_of_date,
            "disclaimerJa": self.disclaimer_ja,
            "disclaimerEn": self.disclaimer_en,
        }


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_fixture_snapshot(path: Path = FIXTURE_PATH) -> DataSnapshot:
    payload = load_json(path)
    stocks = []
    for item in payload["stocks"]:
        stock = dict(item)
        stock.setdefault("priceSource", "fixture")
        stock.setdefault("fundamentalsSource", "fixture")
        stocks.append(stock)
    return DataSnapshot(
        source="fixture",
        source_label="Fixture Data",
        price_source="fixture",
        fundamentals_source="fixture",
        market_symbol=None,
        as_of_date=None,
        disclaimer_ja="現在表示している銘柄および数値はテスト用fixtureです。",
        disclaimer_en="Test data only. Tickers and figures are fictional, not live market prices.",
        assumptions=payload["assumptions"],
        stocks=stocks,
    )


def load_universe(path: Path = UNIVERSE_PATH) -> dict[str, Any]:
    return load_json(path)


def load_fundamentals(path: Path = FUNDAMENTALS_PATH) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    payload = load_json(path)
    stocks = payload.get("stocks") if isinstance(payload, dict) else None
    if stocks is None:
        return {}
    return {str(ticker): value for ticker, value in stocks.items()}


def _payload_from_raw(raw_dir: Path, symbol: str) -> dict[str, Any]:
    path = raw_dir / cache_filename(symbol)
    if not path.exists():
        raise FetchError(f"cached provider file missing: {path}")
    return load_json(path)


def jquants_code(item: dict[str, Any]) -> str:
    if item.get("jquantsCode"):
        return str(item["jquantsCode"])
    ticker = str(item["ticker"])
    if len(ticker) == 4 and ticker.isdigit():
        return ticker + "0"
    return ticker


def edinet_sec_code(item: dict[str, Any]) -> str:
    if item.get("edinetSecCode"):
        return str(item["edinetSecCode"])
    return jquants_code(item)


def _blank_stock(ticker: str, company_name: str) -> dict[str, Any]:
    return {
        "ticker": ticker,
        "companyName": company_name,
        "price": None,
        "priceAsOf": None,
        "priceSource": None,
        "bookValue": None,
        "sharesOutstanding": None,
        "latestRoe": None,
        "roeHistory": None,
        "fundamentalsAsOf": None,
        "fundamentalsSource": None,
        "stockReturns": None,
        "marketReturns": None,
    }


def _apply_price_series(
    stock: dict[str, Any],
    series,
    market_series,
    as_of_dates: list[str],
    source_label: str | None = None,
) -> None:
    last = series.last()
    stock_returns, market_returns = aligned_simple_returns(series, market_series)
    if last is not None:
        stock["price"] = last[1]
        stock["priceAsOf"] = last[0].isoformat()
        as_of_dates.append(stock["priceAsOf"])
        if source_label is not None:
            stock["priceSource"] = source_label
    if stock_returns and market_returns:
        stock["stockReturns"] = stock_returns
        stock["marketReturns"] = market_returns


def _price_complete(series, market_series) -> bool:
    if series.last() is None:
        return False
    stock_returns, market_returns = aligned_simple_returns(series, market_series)
    return len(stock_returns) >= 2 and len(market_returns) >= 2


def _apply_yahoo_prices(
    stock: dict[str, Any],
    *,
    yahoo_symbol: str,
    load_chart,
    market_series,
    as_of_dates: list[str],
) -> None:
    try:
        series = parse_yahoo_chart(load_chart(yahoo_symbol), expected_symbol=yahoo_symbol)
        _apply_price_series(
            stock,
            series,
            market_series,
            as_of_dates,
            source_label="yahoo_chart",
        )
    except ProviderError:
        pass


def _apply_price_waterfall(
    stock: dict[str, Any],
    *,
    jq_code: str,
    yahoo_symbol: str,
    load_bars,
    load_chart,
    market_series,
    as_of_dates: list[str],
    used_price_sources: set[str],
) -> None:
    """J-Quants AdjC bars first, then Yahoo chart. Do not mix series inside one name."""
    chosen_label: str | None = None
    chosen_series = None
    fallback_label: str | None = None
    fallback_series = None

    def take(label: str, series) -> None:
        nonlocal chosen_label, chosen_series, fallback_label, fallback_series
        if chosen_series is not None:
            return
        if _price_complete(series, market_series):
            chosen_label = label
            chosen_series = series
        elif fallback_series is None and series.last() is not None:
            fallback_label = label
            fallback_series = series

    try:
        take("jquants_bars", parse_jquants_bars(load_bars(jq_code), expected_code=jq_code))
    except ProviderError:
        pass
    if chosen_series is None:
        try:
            take(
                "yahoo_chart",
                parse_yahoo_chart(load_chart(yahoo_symbol), expected_symbol=yahoo_symbol),
            )
        except ProviderError:
            pass
    if chosen_series is None:
        chosen_label = fallback_label
        chosen_series = fallback_series
    if chosen_series is not None:
        _apply_price_series(
            stock,
            chosen_series,
            market_series,
            as_of_dates,
            source_label=chosen_label,
        )
        used_price_sources.add(chosen_label)


def _price_source_label(used: set[str]) -> str:
    labels = []
    for name in ("jquants_bars", "yahoo_chart"):
        if name in used:
            labels.append(name)
    return "+".join(labels) if labels else "missing"


def _apply_parsed_fundamentals(
    stock: dict[str, Any],
    fundamentals,
    *,
    source_label: str | None = None,
) -> bool:
    stock["bookValue"] = fundamentals.book_value
    stock["sharesOutstanding"] = fundamentals.shares_outstanding
    stock["latestRoe"] = fundamentals.latest_roe
    stock["roeHistory"] = fundamentals.roe_history
    stock["fundamentalsAsOf"] = fundamentals.fiscal_year_end
    present = _fundamentals_present(fundamentals)
    if present and source_label is not None:
        stock["fundamentalsSource"] = source_label
    return present


def _fundamentals_present(fundamentals) -> bool:
    return fundamentals.book_value is not None or fundamentals.latest_roe is not None


def _fundamentals_complete(fundamentals) -> bool:
    """Enough for residual-income ranking: book, shares, and 3 beginning-book ROEs."""
    history = fundamentals.roe_history
    return (
        fundamentals.book_value is not None
        and fundamentals.shares_outstanding is not None
        and fundamentals.latest_roe is not None
        and isinstance(history, list)
        and len(history) >= 3
    )


def _fundamentals_source_label(used: set[str], overlay: bool) -> str:
    labels = []
    for name in ("edinet_xbrl", "jquants_summary", "yahoo_timeseries"):
        if name in used:
            labels.append(name)
    if overlay:
        labels.append("manual_overlay")
    return "+".join(labels) if labels else "missing"


def _merge_overlay(base: dict[str, Any], overlay: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    """Fill only fields that are still missing. Do not overwrite provider values."""
    merged = dict(base)
    filled = False
    for key in ("bookValue", "sharesOutstanding", "latestRoe", "roeHistory", "fundamentalsAsOf"):
        if merged.get(key) is None and overlay.get(key) is not None:
            merged[key] = overlay[key]
            filled = True
    return merged, filled


def _stamp_overlay_source(stock: dict[str, Any], filled: bool) -> None:
    if not filled:
        return
    current = stock.get("fundamentalsSource")
    if isinstance(current, str) and current:
        stock["fundamentalsSource"] = f"{current}+manual_overlay"
    else:
        stock["fundamentalsSource"] = "manual_overlay"


def load_free_snapshot(
    *,
    universe_path: Path = UNIVERSE_PATH,
    fundamentals_path: Path = FUNDAMENTALS_PATH,
    raw_dir: Path | None = None,
    fundamentals_dir: Path | None = None,
    fetch: bool = False,
    range_: str | None = None,
    fetcher=None,
) -> DataSnapshot:
    """
    Prices from Yahoo chart JSON. Fundamentals from Yahoo annual timeseries.

    EDINET / J-Quants are not called (API keys). Live Stooq HTTP is not used.
    """
    universe = load_universe(universe_path)
    overlay_map = load_fundamentals(fundamentals_path)
    market_symbol = str(universe["marketSymbol"])
    lookback = range_ or str(universe.get("range", "1y"))
    raw_dir = raw_dir or (ROOT / "data" / "raw" / "yahoo")
    fundamentals_dir = fundamentals_dir or (ROOT / "data" / "raw" / "yahoo_fundamentals")

    def load_chart(symbol: str) -> dict[str, Any]:
        if fetch:
            return fetch_yahoo_chart_json(symbol, range_=lookback, fetcher=fetcher)
        return _payload_from_raw(raw_dir, symbol)

    def load_fundamentals_payload(symbol: str) -> dict[str, Any]:
        if fetch:
            return fetch_yahoo_fundamentals_json(symbol, fetcher=fetcher)
        return _payload_from_raw(fundamentals_dir, symbol)

    market_series = parse_yahoo_chart(load_chart(market_symbol), expected_symbol=market_symbol)
    stocks: list[dict[str, Any]] = []
    as_of_dates: list[str] = []
    used_yahoo_fundamentals = False
    used_overlay = False

    for item in universe["stocks"]:
        ticker = str(item["ticker"])
        yahoo_symbol = str(item["yahooSymbol"])
        company_name = str(item["companyName"])
        stock = _blank_stock(ticker, company_name)
        _apply_yahoo_prices(
            stock,
            yahoo_symbol=yahoo_symbol,
            load_chart=load_chart,
            market_series=market_series,
            as_of_dates=as_of_dates,
        )
        try:
            used = _apply_parsed_fundamentals(
                stock,
                parse_yahoo_fundamentals(load_fundamentals_payload(yahoo_symbol)),
                source_label="yahoo_timeseries",
            )
            if used:
                used_yahoo_fundamentals = True
        except ProviderError:
            pass
        stock, filled = _merge_overlay(stock, overlay_map.get(ticker, {}))
        _stamp_overlay_source(stock, filled)
        if filled:
            used_overlay = True
        stocks.append(stock)

    as_of = max(as_of_dates) if as_of_dates else None
    if used_yahoo_fundamentals and used_overlay:
        fundamentals_source = "yahoo_timeseries+manual_overlay"
    elif used_yahoo_fundamentals:
        fundamentals_source = "yahoo_timeseries"
    elif used_overlay:
        fundamentals_source = "manual_overlay"
    else:
        fundamentals_source = "missing"

    return DataSnapshot(
        source="free",
        source_label="Free Data Provider",
        price_source="yahoo_chart",
        fundamentals_source=fundamentals_source,
        market_symbol=market_symbol,
        as_of_date=as_of,
        disclaimer_ja=(
            "価格は Yahoo Finance chart、財務は Yahoo 年次 timeseries（純資産・利益・株数）です。"
            "EDINET / J-Quants は使いません。欠損は 0 にしません。投資助言ではありません。"
        ),
        disclaimer_en=(
            "Prices from Yahoo Finance chart; fundamentals from Yahoo annual timeseries "
            "(equity, net income, shares). EDINET/J-Quants are not used. Missing values "
            "are not replaced with 0. Not investment advice."
        ),
        assumptions={
            "riskFreeRate": float(universe["riskFreeRate"]),
            "equityRiskPremium": float(universe["equityRiskPremium"]),
            "retentionRatio": float(universe["retentionRatio"]),
            "marketReturns": None,
        },
        stocks=stocks,
    )


def load_jquants_snapshot(
    *,
    universe_path: Path = UNIVERSE_PATH,
    fundamentals_path: Path = FUNDAMENTALS_PATH,
    raw_dir: Path | None = None,
    jquants_dir: Path | None = None,
    jquants_bars_dir: Path | None = None,
    fetch: bool = False,
    range_: str | None = None,
    fetcher=None,
    jquants_api_key: str | None = None,
) -> DataSnapshot:
    """
    Prices from J-Quants v2 /equities/bars/daily AdjC, then Yahoo chart.
    Fundamentals from J-Quants v2 /fins/summary.

    Market remains Yahoo Nikkei 225 (J-Quants does not publish Nikkei OHLC).
    Live J-Quants calls need JQUANTS_API_KEY. Missing values are not replaced
    with 0.
    """
    universe = load_universe(universe_path)
    overlay_map = load_fundamentals(fundamentals_path)
    market_symbol = str(universe["marketSymbol"])
    lookback = range_ or str(universe.get("range", "1y"))
    raw_dir = raw_dir or (ROOT / "data" / "raw" / "yahoo")
    jquants_dir = jquants_dir or (ROOT / "data" / "raw" / "jquants")
    jquants_bars_dir = jquants_bars_dir or (ROOT / "data" / "raw" / "jquants_bars")
    bars_from, bars_to = jquants_bars_window(lookback)

    def load_chart(symbol: str) -> dict[str, Any]:
        if fetch:
            return fetch_yahoo_chart_json(symbol, range_=lookback, fetcher=fetcher)
        return _payload_from_raw(raw_dir, symbol)

    def load_summary(code: str) -> dict[str, Any]:
        if fetch:
            return fetch_jquants_summary_json(code, api_key=jquants_api_key, fetcher=fetcher)
        return _payload_from_raw(jquants_dir, code)

    def load_bars(code: str) -> dict[str, Any]:
        if fetch:
            return fetch_jquants_bars_json(
                code,
                from_=bars_from,
                to=bars_to,
                api_key=jquants_api_key,
                fetcher=fetcher,
            )
        return _payload_from_raw(jquants_bars_dir, code)

    market_series = parse_yahoo_chart(load_chart(market_symbol), expected_symbol=market_symbol)
    stocks: list[dict[str, Any]] = []
    as_of_dates: list[str] = []
    used_jquants = False
    used_overlay = False
    used_price_sources: set[str] = set()

    for item in universe["stocks"]:
        ticker = str(item["ticker"])
        yahoo_symbol = str(item["yahooSymbol"])
        code = jquants_code(item)
        stock = _blank_stock(ticker, str(item["companyName"]))
        _apply_price_waterfall(
            stock,
            jq_code=code,
            yahoo_symbol=yahoo_symbol,
            load_bars=load_bars,
            load_chart=load_chart,
            market_series=market_series,
            as_of_dates=as_of_dates,
            used_price_sources=used_price_sources,
        )
        try:
            used = _apply_parsed_fundamentals(
                stock,
                parse_jquants_summary(load_summary(code), expected_code=code),
                source_label="jquants_summary",
            )
            if used:
                used_jquants = True
        except ProviderError:
            pass
        stock, filled = _merge_overlay(stock, overlay_map.get(ticker, {}))
        _stamp_overlay_source(stock, filled)
        if filled:
            used_overlay = True
        stocks.append(stock)

    as_of = max(as_of_dates) if as_of_dates else None
    if used_jquants and used_overlay:
        fundamentals_source = "jquants_summary+manual_overlay"
    elif used_jquants:
        fundamentals_source = "jquants_summary"
    elif used_overlay:
        fundamentals_source = "manual_overlay"
    else:
        fundamentals_source = "missing"

    return DataSnapshot(
        source="jquants",
        source_label="J-Quants",
        price_source=_price_source_label(used_price_sources),
        fundamentals_source=fundamentals_source,
        market_symbol=market_symbol,
        as_of_date=as_of,
        disclaimer_ja=(
            "価格は J-Quants 日足 AdjC（なければ Yahoo chart）。"
            "市場は Yahoo 日経平均。財務は J-Quants 決算短信サマリー（キー必須）です。"
            "欠損は 0 にしません。投資助言ではありません。"
        ),
        disclaimer_en=(
            "Prices from J-Quants daily AdjC (Yahoo chart if bars are missing). "
            "Market is Yahoo Nikkei 225. Fundamentals from J-Quants FY summary "
            "(API key required for live fetch). Missing values are not replaced "
            "with 0. Not investment advice."
        ),
        assumptions={
            "riskFreeRate": float(universe["riskFreeRate"]),
            "equityRiskPremium": float(universe["equityRiskPremium"]),
            "retentionRatio": float(universe["retentionRatio"]),
            "marketReturns": None,
        },
        stocks=stocks,
    )


def load_edinet_snapshot(
    *,
    universe_path: Path = UNIVERSE_PATH,
    fundamentals_path: Path = FUNDAMENTALS_PATH,
    raw_dir: Path | None = None,
    edinet_dir: Path | None = None,
    fetch: bool = False,
    range_: str | None = None,
    fetcher=None,
) -> DataSnapshot:
    """
    Prices from Yahoo chart JSON. Fundamentals from cached EDINET yuho XBRL.

    Live XBRL download is a separate script (EDINET_API_KEY). This loader does
    not crawl filing dates. Missing values are not replaced with 0.
    """
    if fetch:
        raise FetchError("EDINET snapshot does not fetch XBRL; cache files under --edinet-dir")
    universe = load_universe(universe_path)
    overlay_map = load_fundamentals(fundamentals_path)
    market_symbol = str(universe["marketSymbol"])
    lookback = range_ or str(universe.get("range", "1y"))
    raw_dir = raw_dir or (ROOT / "data" / "raw" / "yahoo")
    edinet_dir = edinet_dir or (ROOT / "data" / "raw" / "edinet_xbrl")

    def load_chart(symbol: str) -> dict[str, Any]:
        if fetcher is not None:
            return fetch_yahoo_chart_json(symbol, range_=lookback, fetcher=fetcher)
        return _payload_from_raw(raw_dir, symbol)

    market_series = parse_yahoo_chart(load_chart(market_symbol), expected_symbol=market_symbol)
    stocks: list[dict[str, Any]] = []
    as_of_dates: list[str] = []
    used_edinet = False
    used_overlay = False

    for item in universe["stocks"]:
        ticker = str(item["ticker"])
        yahoo_symbol = str(item["yahooSymbol"])
        code = edinet_sec_code(item)
        stock = _blank_stock(ticker, str(item["companyName"]))
        _apply_yahoo_prices(
            stock,
            yahoo_symbol=yahoo_symbol,
            load_chart=load_chart,
            market_series=market_series,
            as_of_dates=as_of_dates,
        )
        try:
            used = _apply_parsed_fundamentals(
                stock,
                parse_edinet_xbrl_dir(edinet_dir / code),
                source_label="edinet_xbrl",
            )
            if used:
                used_edinet = True
        except ProviderError:
            pass
        stock, filled = _merge_overlay(stock, overlay_map.get(ticker, {}))
        _stamp_overlay_source(stock, filled)
        if filled:
            used_overlay = True
        stocks.append(stock)

    as_of = max(as_of_dates) if as_of_dates else None
    if used_edinet and used_overlay:
        fundamentals_source = "edinet_xbrl+manual_overlay"
    elif used_edinet:
        fundamentals_source = "edinet_xbrl"
    elif used_overlay:
        fundamentals_source = "manual_overlay"
    else:
        fundamentals_source = "missing"

    return DataSnapshot(
        source="edinet",
        source_label="EDINET XBRL",
        price_source="yahoo_chart",
        fundamentals_source=fundamentals_source,
        market_symbol=market_symbol,
        as_of_date=as_of,
        disclaimer_ja=(
            "価格は Yahoo Finance chart、財務は EDINET 有報 XBRL（キー必須の取得）です。"
            "欠損は 0 にしません。投資助言ではありません。"
        ),
        disclaimer_en=(
            "Prices from Yahoo Finance chart; fundamentals from EDINET annual "
            "XBRL (API key required to download). Missing values are not replaced "
            "with 0. Not investment advice."
        ),
        assumptions={
            "riskFreeRate": float(universe["riskFreeRate"]),
            "equityRiskPremium": float(universe["equityRiskPremium"]),
            "retentionRatio": float(universe["retentionRatio"]),
            "marketReturns": None,
        },
        stocks=stocks,
    )


def load_auto_snapshot(
    *,
    universe_path: Path = UNIVERSE_PATH,
    fundamentals_path: Path = FUNDAMENTALS_PATH,
    raw_dir: Path | None = None,
    fundamentals_dir: Path | None = None,
    jquants_dir: Path | None = None,
    jquants_bars_dir: Path | None = None,
    edinet_dir: Path | None = None,
    range_: str | None = None,
    fetcher=None,
) -> DataSnapshot:
    """
    Prices per name, first complete series: J-Quants daily AdjC → Yahoo chart.
    Market is Yahoo Nikkei 225. Fundamentals per name, first complete source:

    EDINET yuho XBRL → J-Quants FY summary → Yahoo annual timeseries → overlay.

    Complete prices means a last close and at least two aligned market returns.
    Complete fundamentals means book, shares, and 3 beginning-book ROE years.
    A partial higher-tier cache does not block a complete lower-tier cache.
    Sources are not mixed inside one name. If nothing is complete, the first
    partial is kept. Missing stays missing. Cache only.
    """
    universe = load_universe(universe_path)
    overlay_map = load_fundamentals(fundamentals_path)
    market_symbol = str(universe["marketSymbol"])
    lookback = range_ or str(universe.get("range", "1y"))
    raw_dir = raw_dir or (ROOT / "data" / "raw" / "yahoo")
    fundamentals_dir = fundamentals_dir or (ROOT / "data" / "raw" / "yahoo_fundamentals")
    jquants_dir = jquants_dir or (ROOT / "data" / "raw" / "jquants")
    jquants_bars_dir = jquants_bars_dir or (ROOT / "data" / "raw" / "jquants_bars")
    edinet_dir = edinet_dir or (ROOT / "data" / "raw" / "edinet_xbrl")

    def load_chart(symbol: str) -> dict[str, Any]:
        if fetcher is not None:
            return fetch_yahoo_chart_json(symbol, range_=lookback, fetcher=fetcher)
        return _payload_from_raw(raw_dir, symbol)

    def load_bars(code: str) -> dict[str, Any]:
        return _payload_from_raw(jquants_bars_dir, code)

    market_series = parse_yahoo_chart(load_chart(market_symbol), expected_symbol=market_symbol)
    stocks: list[dict[str, Any]] = []
    as_of_dates: list[str] = []
    used_sources: set[str] = set()
    used_price_sources: set[str] = set()
    used_overlay = False

    for item in universe["stocks"]:
        ticker = str(item["ticker"])
        yahoo_symbol = str(item["yahooSymbol"])
        stock = _blank_stock(ticker, str(item["companyName"]))
        jq_code = jquants_code(item)
        _apply_price_waterfall(
            stock,
            jq_code=jq_code,
            yahoo_symbol=yahoo_symbol,
            load_bars=load_bars,
            load_chart=load_chart,
            market_series=market_series,
            as_of_dates=as_of_dates,
            used_price_sources=used_price_sources,
        )
        chosen_label: str | None = None
        chosen_fundamentals = None
        fallback_label: str | None = None
        fallback_fundamentals = None
        edinet_code = edinet_sec_code(item)

        def take(label: str, fundamentals) -> None:
            nonlocal chosen_label, chosen_fundamentals, fallback_label, fallback_fundamentals
            if chosen_fundamentals is not None:
                return
            if _fundamentals_complete(fundamentals):
                chosen_label = label
                chosen_fundamentals = fundamentals
            elif fallback_fundamentals is None and _fundamentals_present(fundamentals):
                fallback_label = label
                fallback_fundamentals = fundamentals

        try:
            take("edinet_xbrl", parse_edinet_xbrl_dir(edinet_dir / edinet_code))
        except ProviderError:
            pass
        if chosen_fundamentals is None:
            try:
                take(
                    "jquants_summary",
                    parse_jquants_summary(
                        _payload_from_raw(jquants_dir, jq_code),
                        expected_code=jq_code,
                    ),
                )
            except ProviderError:
                pass
        if chosen_fundamentals is None:
            try:
                take(
                    "yahoo_timeseries",
                    parse_yahoo_fundamentals(_payload_from_raw(fundamentals_dir, yahoo_symbol)),
                )
            except ProviderError:
                pass
        if chosen_fundamentals is None:
            chosen_label = fallback_label
            chosen_fundamentals = fallback_fundamentals
        if chosen_fundamentals is not None:
            _apply_parsed_fundamentals(
                stock,
                chosen_fundamentals,
                source_label=chosen_label,
            )
            used_sources.add(chosen_label)
        stock, filled = _merge_overlay(stock, overlay_map.get(ticker, {}))
        _stamp_overlay_source(stock, filled)
        if filled:
            used_overlay = True
        stocks.append(stock)

    as_of = max(as_of_dates) if as_of_dates else None
    return DataSnapshot(
        source="auto",
        source_label="Auto Data Provider",
        price_source=_price_source_label(used_price_sources),
        fundamentals_source=_fundamentals_source_label(used_sources, used_overlay),
        market_symbol=market_symbol,
        as_of_date=as_of,
        disclaimer_ja=(
            "価格は銘柄ごとに J-Quants 日足 AdjC、なければ Yahoo chart。"
            "市場は Yahoo 日経平均。財務は EDINET XBRL、J-Quants、Yahoo timeseries "
            "の順で最初に揃ったソースです。欠損は 0 にしません。投資助言ではありません。"
        ),
        disclaimer_en=(
            "Prices use the first complete series per name: J-Quants daily AdjC, "
            "then Yahoo chart. Market is Yahoo Nikkei 225. Fundamentals use the "
            "first complete source per name: EDINET XBRL, then J-Quants, then "
            "Yahoo timeseries. Missing values are not replaced with 0. "
            "Not investment advice."
        ),
        assumptions={
            "riskFreeRate": float(universe["riskFreeRate"]),
            "equityRiskPremium": float(universe["equityRiskPremium"]),
            "retentionRatio": float(universe["retentionRatio"]),
            "marketReturns": None,
        },
        stocks=stocks,
    )


def load_stooq_csv_snapshot(
    *,
    stock_csv: Path,
    market_csv: Path,
    ticker: str,
    company_name: str,
) -> tuple[float | None, str | None, list[float], list[float]]:
    """Test/helper path for operator-supplied Stooq CSVs."""
    stock_series = parse_stooq_csv(stock_csv.read_text(encoding="utf-8"), symbol=ticker)
    market_series = parse_stooq_csv(market_csv.read_text(encoding="utf-8"), symbol="market")
    last = stock_series.last()
    stock_returns, market_returns = aligned_simple_returns(stock_series, market_series)
    price = last[1] if last else None
    as_of = last[0].isoformat() if last else None
    return price, as_of, stock_returns, market_returns
