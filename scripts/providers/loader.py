"""Load engine-ready snapshots. Fixture remains the default deterministic source."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from providers.errors import FetchError, ProviderError
from providers.http import cache_filename, fetch_yahoo_chart_json
from providers.series import aligned_simple_returns
from providers.stooq_csv import parse_stooq_csv
from providers.yahoo_chart import parse_yahoo_chart

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
        stocks=payload["stocks"],
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


def _yahoo_payload_from_raw(raw_dir: Path, symbol: str) -> dict[str, Any]:
    path = raw_dir / cache_filename(symbol)
    if not path.exists():
        raise FetchError(f"cached Yahoo chart missing: {path}")
    return load_json(path)


def load_free_snapshot(
    *,
    universe_path: Path = UNIVERSE_PATH,
    fundamentals_path: Path = FUNDAMENTALS_PATH,
    raw_dir: Path | None = None,
    fetch: bool = False,
    range_: str | None = None,
    fetcher=None,
) -> DataSnapshot:
    """
    Prices from Yahoo chart JSON (cached or fetched). Fundamentals are overlay-only.

    EDINET / J-Quants are out of scope: they need API keys.
    Live Stooq HTTP is not used: it returns a bot-wall from this environment.
    """
    universe = load_universe(universe_path)
    fundamentals = load_fundamentals(fundamentals_path)
    market_symbol = str(universe["marketSymbol"])
    lookback = range_ or str(universe.get("range", "1y"))
    raw_dir = raw_dir or (ROOT / "data" / "raw" / "yahoo")

    def load_symbol(symbol: str) -> dict[str, Any]:
        if fetch:
            return fetch_yahoo_chart_json(symbol, range_=lookback, fetcher=fetcher)
        return _yahoo_payload_from_raw(raw_dir, symbol)

    market_series = parse_yahoo_chart(load_symbol(market_symbol), expected_symbol=market_symbol)
    stocks: list[dict[str, Any]] = []
    as_of_dates: list[str] = []

    for item in universe["stocks"]:
        ticker = str(item["ticker"])
        yahoo_symbol = str(item["yahooSymbol"])
        company_name = str(item["companyName"])
        overlay = fundamentals.get(ticker, {})
        stock: dict[str, Any] = {
            "ticker": ticker,
            "companyName": company_name,
            "price": None,
            "priceAsOf": None,
            "bookValue": overlay.get("bookValue"),
            "sharesOutstanding": overlay.get("sharesOutstanding"),
            "latestRoe": overlay.get("latestRoe"),
            "roeHistory": overlay.get("roeHistory"),
            "stockReturns": None,
            "marketReturns": None,
        }
        try:
            series = parse_yahoo_chart(load_symbol(yahoo_symbol), expected_symbol=yahoo_symbol)
            last = series.last()
            stock_returns, market_returns = aligned_simple_returns(series, market_series)
            if last is not None:
                stock["price"] = last[1]
                stock["priceAsOf"] = last[0].isoformat()
                as_of_dates.append(stock["priceAsOf"])
            if stock_returns and market_returns:
                stock["stockReturns"] = stock_returns
                stock["marketReturns"] = market_returns
        except ProviderError:
            # Leave price/returns as None. The engine records exclusion reasons.
            pass
        stocks.append(stock)

    as_of = max(as_of_dates) if as_of_dates else None
    fundamentals_source = "manual_overlay" if fundamentals else "missing"
    return DataSnapshot(
        source="free",
        source_label="Free Data Provider",
        price_source="yahoo_chart",
        fundamentals_source=fundamentals_source,
        market_symbol=market_symbol,
        as_of_date=as_of,
        disclaimer_ja=(
            "価格は無料の Yahoo Finance chart API です。財務（EDINET / J-Quants）はこのPhaseでは取得しません。"
            "財務が無い銘柄はランキング対象外です。投資助言ではありません。"
        ),
        disclaimer_en=(
            "Prices from the free Yahoo Finance chart API. Fundamentals are not fetched "
            "in this phase. Names without book value/ROE are excluded from ranking. "
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
