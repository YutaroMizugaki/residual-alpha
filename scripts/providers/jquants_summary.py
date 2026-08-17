"""J-Quants v2 /fins/summary. Annual FY rows only. Empty strings stay missing."""

from __future__ import annotations

import json
from datetime import date
from typing import Any

from providers.errors import BotWallError, FetchError, InvalidPriceDataError
from providers.fundamentals_common import (
    JPY_MILLION,
    Fundamentals,
    as_date,
    beginning_book_roes,
    optional_float,
    pack_roes,
)


def codes_match(row_code: str, expected: str) -> bool:
    left = row_code.strip()
    right = expected.strip()
    if left == right:
        return True
    if len(left) == 4 and len(right) == 5 and right == left + "0":
        return True
    if len(right) == 4 and len(left) == 5 and left == right + "0":
        return True
    return False


def _doc_rank(doc_type: str) -> int:
    text = doc_type or ""
    if "NonConsolidated" in text or "Non-Consolidated" in text:
        return 0
    if "Consolidated" in text:
        return 2
    return 1


def _select_fy_rows(rows: list[dict[str, Any]], expected_code: str | None) -> dict[date, dict[str, Any]]:
    selected: dict[date, tuple[int, str, str, dict[str, Any]]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        if expected_code and not codes_match(str(row.get("Code") or ""), expected_code):
            continue
        if str(row.get("CurPerType") or "") != "FY":
            continue
        period_end = row.get("CurPerEn")
        if not period_end:
            continue
        try:
            fy_end = as_date(str(period_end))
        except ValueError:
            continue
        rank = _doc_rank(str(row.get("DocType") or ""))
        disc_date = str(row.get("DiscDate") or "")
        disc_no = str(row.get("DiscNo") or "")
        previous = selected.get(fy_end)
        marker = (rank, disc_date, disc_no, row)
        if previous is None or marker[:3] > previous[:3]:
            selected[fy_end] = marker
    return {fy_end: item[3] for fy_end, item in selected.items()}


def parse_jquants_summary(payload: Any, *, expected_code: str | None = None) -> Fundamentals:
    if isinstance(payload, str):
        text = payload.lstrip()
        if text.startswith("<!") or text.startswith("<html"):
            raise BotWallError("J-Quants summary returned HTML instead of JSON")
        try:
            payload = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise FetchError("J-Quants summary payload is not JSON") from exc
    if not isinstance(payload, dict):
        raise InvalidPriceDataError("J-Quants summary payload is not an object")
    if payload.get("data") is None:
        raise FetchError("J-Quants summary data is missing")
    rows = payload.get("data")
    if not isinstance(rows, list):
        raise InvalidPriceDataError("J-Quants summary data is invalid")

    fy_rows = _select_fy_rows(rows, expected_code)
    equity: dict[date, float] = {}
    income: dict[date, float] = {}
    shares_by_date: dict[date, float] = {}

    for fy_end, row in fy_rows.items():
        shareholders = optional_float(row.get("ShEq"))
        equity_all = optional_float(row.get("Eq"))
        book = shareholders if shareholders is not None else equity_all
        if book is not None:
            equity[fy_end] = book
        profit = optional_float(row.get("NP"))
        if profit is not None:
            income[fy_end] = profit
        issued = optional_float(row.get("ShOutFY"))
        treasury = optional_float(row.get("TrShFY"))
        if issued is not None and treasury is not None:
            outstanding = issued - treasury
            if outstanding > 0:
                shares_by_date[fy_end] = outstanding

    book_value = None
    fiscal_year_end = None
    if equity:
        latest_eq_date = max(equity)
        latest_equity = equity[latest_eq_date]
        if latest_equity > 0:
            book_value = latest_equity / JPY_MILLION
            fiscal_year_end = latest_eq_date.isoformat()

    shares_outstanding = None
    if shares_by_date:
        latest_shares = shares_by_date[max(shares_by_date)]
        shares_outstanding = latest_shares / JPY_MILLION

    roes = beginning_book_roes(equity, income)
    latest_roe, roe_history = pack_roes(roes)
    return Fundamentals(
        book_value=book_value,
        shares_outstanding=shares_outstanding,
        latest_roe=latest_roe,
        roe_history=roe_history,
        fiscal_year_end=fiscal_year_end,
    )
