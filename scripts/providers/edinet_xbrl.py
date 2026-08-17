"""EDINET yuho XBRL instance parser. Stdlib only. Missing stays missing."""

from __future__ import annotations

import io
import zipfile
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from xml.etree import ElementTree as ET

from providers.errors import BotWallError, FetchError, InvalidPriceDataError
from providers.fundamentals_common import (
    JPY_MILLION,
    MAX_YEAR_DAYS,
    MIN_YEAR_DAYS,
    Fundamentals,
    as_date,
    beginning_book_roes,
    optional_float,
    pack_roes,
)

MAX_ZIP_MEMBER = 20 * 1024 * 1024
YearMaps = tuple[dict[date, float], dict[date, float], dict[date, float], dict[date, float]]

EQUITY_NAMES = (
    "EquityAttributableToOwnersOfParentIFRS",
    "EquityAttributableToOwnersOfParent",
    "ShareholdersEquity",
    "NetAssets",
)
INCOME_NAMES = (
    "ProfitLossAttributableToOwnersOfParentIFRS",
    "ProfitLossAttributableToOwnersOfParent",
    "ProfitAttributableToOwnersOfParent",
)
ISSUED_SHARE_NAMES = (
    "NumberOfIssuedAndOutstandingSharesAtTheEndOfFiscalYearIncludingTreasuryStockDEI",
    "NumberOfIssuedAndOutstandingSharesAtTheEndOfFiscalYearIncludingTreasuryStock",
    "TotalNumberOfIssuedSharesSummaryOfBusinessResults",
)
TREASURY_SHARE_NAMES = (
    "NumberOfTreasuryStockAtTheEndOfFiscalYearDEI",
    "NumberOfTreasuryStockAtTheEndOfFiscalYear",
)


@dataclass(frozen=True)
class _Context:
    id: str
    instant: date | None
    start: date | None
    end: date | None
    consolidated: bool
    forecast: bool


def local_name(tag: str) -> str:
    if tag.startswith("{"):
        return tag.split("}", 1)[1]
    return tag.split(":")[-1]


def _text(elem: ET.Element | None) -> str:
    if elem is None or elem.text is None:
        return ""
    return elem.text.strip()


def _is_nil(elem: ET.Element) -> bool:
    raw = elem.attrib.get("nil") or elem.attrib.get("{http://www.w3.org/2001/XMLSchema-instance}nil")
    return str(raw).lower() == "true"


def _fact_number(elem: ET.Element) -> float | None:
    if _is_nil(elem):
        return None
    return optional_float(_text(elem))


def _blob(elem: ET.Element) -> str:
    parts = [elem.get("id") or "", local_name(elem.tag)]
    for child in elem.iter():
        parts.append(local_name(child.tag))
        parts.append(_text(child))
    return " ".join(parts)


def _parse_contexts(root: ET.Element) -> dict[str, _Context]:
    out: dict[str, _Context] = {}
    for elem in root.iter():
        if local_name(elem.tag) != "context":
            continue
        ctx_id = elem.get("id")
        if not ctx_id:
            continue
        instant = start = end = None
        for child in elem.iter():
            name = local_name(child.tag)
            value = _text(child)
            if not value:
                continue
            try:
                parsed = as_date(value)
            except ValueError:
                continue
            if name == "instant":
                instant = parsed
            elif name == "startDate":
                start = parsed
            elif name == "endDate":
                end = parsed
        blob = _blob(elem)
        forecast = any(token in blob for token in ("Forecast", "Budget", "NextYear"))
        noncons = "NonConsolidated" in blob or "Non-Consolidated" in blob
        out[ctx_id] = _Context(
            id=ctx_id,
            instant=instant,
            start=start,
            end=end,
            consolidated=not noncons,
            forecast=forecast,
        )
    return out


def _parse_units(root: ET.Element) -> dict[str, str]:
    units: dict[str, str] = {}
    for elem in root.iter():
        if local_name(elem.tag) != "unit":
            continue
        unit_id = elem.get("id")
        if not unit_id:
            continue
        if any(local_name(child.tag) == "divide" for child in elem.iter()):
            units[unit_id] = "DIVIDE"
            continue
        measures = [_text(child) for child in elem.iter() if local_name(child.tag) == "measure"]
        units[unit_id] = " ".join(m for m in measures if m)
    return units


def _is_jpy(measure: str) -> bool:
    text = measure.lower()
    return text.endswith("jpy") or ":jpy" in text or text == "jpy"


def _is_shares(measure: str) -> bool:
    return "share" in measure.lower()


def _current_year_end(contexts: dict[str, _Context]) -> date | None:
    ends: list[date] = []
    for ctx in contexts.values():
        if "CurrentYear" not in ctx.id or ctx.forecast:
            continue
        marker = ctx.instant or ctx.end
        if marker is not None:
            ends.append(marker)
    return max(ends) if ends else None


def _period_for_fact(elem: ET.Element, ctx: _Context, current_end: date | None) -> date | None:
    name = local_name(elem.tag)
    if name.endswith("DEI") and "FilingDate" in ctx.id:
        return current_end
    if ctx.instant is not None:
        return ctx.instant
    if ctx.end is not None:
        return ctx.end
    return None


def _pick_named(
    root: ET.Element,
    contexts: dict[str, _Context],
    units: dict[str, str],
    names: tuple[str, ...],
    *,
    kind: str,
    require_jpy: bool,
    require_shares: bool,
    current_end: date | None,
) -> dict[date, float]:
    name_rank = {name: index for index, name in enumerate(names)}
    chosen: dict[date, tuple[int, int, float]] = {}
    for elem in root.iter():
        local = local_name(elem.tag)
        if local not in name_rank:
            continue
        ctx = contexts.get(elem.get("contextRef") or "")
        if ctx is None or ctx.forecast:
            continue
        if kind == "instant" and ctx.instant is None and "FilingDate" not in ctx.id:
            continue
        if kind == "duration":
            if ctx.start is None or ctx.end is None:
                continue
            span = (ctx.end - ctx.start).days
            if span < MIN_YEAR_DAYS or span > MAX_YEAR_DAYS:
                continue
        unit = units.get(elem.get("unitRef") or "")
        if unit == "DIVIDE":
            continue
        if require_jpy and unit and not _is_jpy(unit):
            continue
        if require_shares and unit and not _is_shares(unit):
            continue
        number = _fact_number(elem)
        if number is None:
            continue
        period = _period_for_fact(elem, ctx, current_end)
        if period is None:
            continue
        rank = name_rank[local]
        consol_rank = 0 if ctx.consolidated else 1
        previous = chosen.get(period)
        if previous is None or (rank, consol_rank) < (previous[0], previous[1]):
            chosen[period] = (rank, consol_rank, number)
    return {period: item[2] for period, item in chosen.items()}


def _maps_from_xml(payload: str) -> YearMaps:
    text = payload.lstrip()
    if text.startswith("<!") or text.startswith("<html"):
        raise BotWallError("EDINET XBRL returned HTML instead of XML")
    try:
        root = ET.fromstring(payload)
    except ET.ParseError as exc:
        raise FetchError("EDINET XBRL XML is invalid") from exc
    contexts = _parse_contexts(root)
    units = _parse_units(root)
    current_end = _current_year_end(contexts)
    equity = _pick_named(
        root, contexts, units, EQUITY_NAMES,
        kind="instant", require_jpy=True, require_shares=False, current_end=current_end,
    )
    income = _pick_named(
        root, contexts, units, INCOME_NAMES,
        kind="duration", require_jpy=True, require_shares=False, current_end=current_end,
    )
    issued = _pick_named(
        root, contexts, units, ISSUED_SHARE_NAMES,
        kind="instant", require_jpy=False, require_shares=True, current_end=current_end,
    )
    treasury = _pick_named(
        root, contexts, units, TREASURY_SHARE_NAMES,
        kind="instant", require_jpy=False, require_shares=True, current_end=current_end,
    )
    return equity, income, issued, treasury


def _fundamentals_from_maps(
    equity: dict[date, float],
    income: dict[date, float],
    issued: dict[date, float],
    treasury: dict[date, float],
) -> Fundamentals:
    shares: dict[date, float] = {}
    for period in set(issued) | set(treasury):
        issued_n = issued.get(period)
        treasury_n = treasury.get(period)
        if issued_n is None or treasury_n is None:
            continue
        outstanding = issued_n - treasury_n
        if outstanding > 0:
            shares[period] = outstanding

    book_value = None
    fiscal_year_end = None
    if equity:
        latest = max(equity)
        if equity[latest] > 0:
            book_value = equity[latest] / JPY_MILLION
            fiscal_year_end = latest.isoformat()

    shares_outstanding = None
    if shares:
        shares_outstanding = shares[max(shares)] / JPY_MILLION

    latest_roe, roe_history = pack_roes(beginning_book_roes(equity, income))
    return Fundamentals(
        book_value=book_value,
        shares_outstanding=shares_outstanding,
        latest_roe=latest_roe,
        roe_history=roe_history,
        fiscal_year_end=fiscal_year_end,
    )


def zip_instance_names(zf: zipfile.ZipFile) -> list[str]:
    names = [name for name in zf.namelist() if name.lower().endswith(".xbrl") and not name.endswith("/")]
    public = [name for name in names if "PublicDoc" in name.replace("\\", "/")]
    pool = public or [name for name in names if "AuditDoc" not in name.replace("\\", "/")]
    ranked: list[tuple[int, str]] = []
    for name in pool:
        lower = name.lower()
        score = 0
        if "publicdoc" in lower:
            score += 3
        if "jpcrp030000" in lower or "-asr-" in lower:
            score += 2
        if "jpigp" in lower:
            score += 1
        ranked.append((score, name))
    ranked.sort(reverse=True)
    return [name for _, name in ranked]


def _maps_from_zip(data: bytes) -> YearMaps:
    sniff = data.lstrip()[:80].lower()
    if sniff.startswith(b"<!doctype") or sniff.startswith(b"<html"):
        raise BotWallError("EDINET XBRL zip returned HTML instead of a zip")
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise FetchError("EDINET XBRL payload is not a zip") from exc
    names = zip_instance_names(zf)
    if not names:
        raise FetchError("EDINET zip has no XBRL instance")
    equity: dict[date, float] = {}
    income: dict[date, float] = {}
    issued: dict[date, float] = {}
    treasury: dict[date, float] = {}
    parsed_any = False
    for name in names:
        info = zf.getinfo(name)
        if info.file_size > MAX_ZIP_MEMBER:
            continue
        text = zf.read(name).decode("utf-8", errors="replace")
        try:
            eq, ni, sh, tr = _maps_from_xml(text)
        except (FetchError, BotWallError, InvalidPriceDataError):
            continue
        parsed_any = True
        equity.update(eq)
        income.update(ni)
        issued.update(sh)
        treasury.update(tr)
    if not parsed_any:
        raise FetchError("EDINET zip XBRL instance could not be parsed")
    return equity, income, issued, treasury


def parse_edinet_instance_xml(payload: str) -> Fundamentals:
    equity, income, issued, treasury = _maps_from_xml(payload)
    return _fundamentals_from_maps(equity, income, issued, treasury)


def parse_edinet_xbrl_zip(data: bytes) -> Fundamentals:
    equity, income, issued, treasury = _maps_from_zip(data)
    return _fundamentals_from_maps(equity, income, issued, treasury)


def parse_edinet_xbrl(payload: str | bytes | Path) -> Fundamentals:
    if isinstance(payload, Path):
        data = payload.read_bytes()
        if payload.suffix.lower() == ".zip" or data[:2] == b"PK":
            return parse_edinet_xbrl_zip(data)
        return parse_edinet_instance_xml(data.decode("utf-8"))
    if isinstance(payload, bytes):
        if payload[:2] == b"PK":
            return parse_edinet_xbrl_zip(payload)
        return parse_edinet_instance_xml(payload.decode("utf-8", errors="replace"))
    stripped = payload.lstrip()
    if stripped.startswith("<"):
        return parse_edinet_instance_xml(payload)
    raise FetchError("EDINET XBRL payload is not XML")


def parse_edinet_xbrl_dir(path: Path) -> Fundamentals:
    if not path.exists():
        raise FetchError(f"cached EDINET XBRL missing: {path}")
    files = [path] if path.is_file() else sorted(
        p for p in path.iterdir() if p.suffix.lower() in {".xbrl", ".xml", ".zip"}
    )
    if not files:
        raise FetchError(f"cached EDINET XBRL missing: {path}")
    equity: dict[date, float] = {}
    income: dict[date, float] = {}
    issued: dict[date, float] = {}
    treasury: dict[date, float] = {}
    parsed_any = False
    for file in files:
        data = file.read_bytes()
        try:
            if file.suffix.lower() == ".zip" or data[:2] == b"PK":
                eq, ni, sh, tr = _maps_from_zip(data)
            else:
                eq, ni, sh, tr = _maps_from_xml(data.decode("utf-8"))
        except (FetchError, BotWallError, InvalidPriceDataError, UnicodeDecodeError):
            continue
        equity.update(eq)
        income.update(ni)
        issued.update(sh)
        treasury.update(tr)
        parsed_any = True
    if not parsed_any:
        raise FetchError(f"cached EDINET XBRL missing usable instance: {path}")
    return _fundamentals_from_maps(equity, income, issued, treasury)
