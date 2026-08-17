from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest

from models.pipeline import evaluate_universe
from providers.edinet_xbrl import parse_edinet_instance_xml, parse_edinet_xbrl_dir, parse_edinet_xbrl_zip
from providers.errors import BotWallError, FetchError
from providers.http import edinet_xbrl_url, fetch_edinet_xbrl_zip, redact_url
from providers.loader import load_edinet_snapshot

ROOT = Path(__file__).resolve().parents[1]
YAHOO_DIR = ROOT / "tests" / "data" / "yahoo"
XBRL_DIR = ROOT / "tests" / "data" / "edinet_xbrl"

LABELS = ("CurrentYear", "Prior1Year", "Prior2Year", "Prior3Year")


def make_ifrs_xbrl(rows: list[tuple[str, str, str, str, str]], *, extra: str = "") -> str:
    """rows: latest-first (end, start, equity, profit, issued). Treasury defaults to 0."""
    contexts = [
        """  <xbrli:unit id="JPY"><xbrli:measure>iso4217:JPY</xbrli:measure></xbrli:unit>
  <xbrli:unit id="Shares"><xbrli:measure>xbrli:shares</xbrli:measure></xbrli:unit>
"""
    ]
    facts = []
    for label, (end, start, equity, profit, issued) in zip(LABELS, rows):
        contexts.append(
            f"""  <xbrli:context id="{label}Instant">
    <xbrli:entity><xbrli:identifier scheme="http://disclosure.edinet-fsa.go.jp">E00000</xbrli:identifier></xbrli:entity>
    <xbrli:period><xbrli:instant>{end}</xbrli:instant></xbrli:period>
  </xbrli:context>
  <xbrli:context id="{label}Duration">
    <xbrli:entity><xbrli:identifier scheme="http://disclosure.edinet-fsa.go.jp">E00000</xbrli:identifier></xbrli:entity>
    <xbrli:period><xbrli:startDate>{start}</xbrli:startDate><xbrli:endDate>{end}</xbrli:endDate></xbrli:period>
  </xbrli:context>
"""
        )
        facts.append(
            f"""  <jpigp:EquityAttributableToOwnersOfParentIFRS contextRef="{label}Instant" unitRef="JPY" decimals="-6">{equity}</jpigp:EquityAttributableToOwnersOfParentIFRS>
  <jpigp:ProfitLossAttributableToOwnersOfParentIFRS contextRef="{label}Duration" unitRef="JPY" decimals="-6">{profit}</jpigp:ProfitLossAttributableToOwnersOfParentIFRS>
  <jpdei:NumberOfIssuedAndOutstandingSharesAtTheEndOfFiscalYearIncludingTreasuryStockDEI contextRef="{label}Instant" unitRef="Shares" decimals="0">{issued}</jpdei:NumberOfIssuedAndOutstandingSharesAtTheEndOfFiscalYearIncludingTreasuryStockDEI>
  <jpdei:NumberOfTreasuryStockAtTheEndOfFiscalYearDEI contextRef="{label}Instant" unitRef="Shares" decimals="0">0</jpdei:NumberOfTreasuryStockAtTheEndOfFiscalYearDEI>
"""
        )
    return (
        """<?xml version="1.0" encoding="UTF-8"?>
<xbrli:xbrl xmlns:xbrli="http://www.xbrl.org/2003/instance" xmlns:jpigp="http://disclosure.edinet-fsa.go.jp/taxonomy/jpigp/2025-11-01/jpigp_cor" xmlns:jpdei="http://disclosure.edinet-fsa.go.jp/taxonomy/jpdei/2013-08-31/jpdei_cor" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
"""
        + "".join(contexts)
        + "".join(facts)
        + extra
        + "</xbrli:xbrl>\n"
    )


TOYOTA_ROWS = [
    ("2026-03-31", "2025-04-01", "39918854000000", "3848098000000", "13033384474"),
    ("2025-03-31", "2024-04-01", "35924826000000", "4765086000000", "13048929774"),
    ("2024-03-31", "2023-04-01", "34220991000000", "4944933000000", "13474172027"),
    ("2023-03-31", "2022-04-01", "28338706000000", "2451318000000", "13565179729"),
]
SONY_ROWS = [
    ("2026-03-31", "2025-04-01", "8119011000000", "-326865000000", "5907667254"),
    ("2025-03-31", "2024-04-01", "8179745000000", "1141600000000", "6025003795"),
    ("2024-03-31", "2023-04-01", "7587177000000", "970573000000", "6107244430"),
    ("2023-03-31", "2022-04-01", "6598537000000", "1005277000000", "6172487800"),
]
SOFTBANK_ROWS = [
    ("2026-03-31", "2025-04-01", "17621823000000", "5002271000000", "5698923701"),
    ("2025-03-31", "2024-04-01", "11561541000000", "1153332000000", "5750385224"),
    ("2024-03-31", "2023-04-01", "11162125000000", "-227646000000", "5863701596"),
    ("2023-03-31", "2022-04-01", "9029849000000", "-970144000000", "5852188920"),
]


def test_edinet_xbrl_toyota_units_and_beginning_roe():
    xml = (XBRL_DIR / "72030" / "instance.xbrl").read_text(encoding="utf-8")
    fundamentals = parse_edinet_instance_xml(xml)
    assert fundamentals.book_value == pytest.approx(39_918_854.0)
    assert fundamentals.shares_outstanding == pytest.approx(13_033.384474)
    assert fundamentals.fiscal_year_end == "2026-03-31"
    assert fundamentals.roe_history is not None
    assert len(fundamentals.roe_history) == 3
    assert fundamentals.latest_roe == pytest.approx(3_848_098_000_000.0 / 35_924_826_000_000.0)


def test_edinet_xbrl_prefers_consolidated_over_nonconsolidated():
    extra = """
  <xbrli:context id="CurrentYearInstant_NonConsolidatedMember">
    <xbrli:entity><xbrli:identifier scheme="http://disclosure.edinet-fsa.go.jp">E00000</xbrli:identifier></xbrli:entity>
    <xbrli:period><xbrli:instant>2026-03-31</xbrli:instant></xbrli:period>
    <xbrli:scenario><xbrldi:explicitMember xmlns:xbrldi="http://xbrl.org/2006/xbrldi" dimension="jpigp:ConsolidatedOrNonConsolidatedAxis">jpigp:NonConsolidatedMember</xbrldi:explicitMember></xbrli:scenario>
  </xbrli:context>
  <jpigp:EquityAttributableToOwnersOfParentIFRS contextRef="CurrentYearInstant_NonConsolidatedMember" unitRef="JPY" decimals="0">1</jpigp:EquityAttributableToOwnersOfParentIFRS>
"""
    xml = make_ifrs_xbrl(TOYOTA_ROWS, extra=extra)
    fundamentals = parse_edinet_instance_xml(xml)
    assert fundamentals.book_value == pytest.approx(39_918_854.0)


def test_edinet_xbrl_nil_profit_is_missing_not_zero():
    xml = make_ifrs_xbrl(
        [
            ("2026-03-31", "2025-04-01", "1300000000", "150000000", "100000000"),
            ("2025-03-31", "2024-04-01", "1100000000", "nil", "100000000"),
            ("2024-03-31", "2023-04-01", "1000000000", "120000000", "100000000"),
        ]
    )
    xml = xml.replace(
        'contextRef="Prior1YearDuration" unitRef="JPY" decimals="-6">nil</jpigp:ProfitLossAttributableToOwnersOfParentIFRS>',
        'contextRef="Prior1YearDuration" unitRef="JPY" xsi:nil="true"/>',
    )
    fundamentals = parse_edinet_instance_xml(xml)
    assert fundamentals.roe_history is not None
    assert 0 not in fundamentals.roe_history
    assert fundamentals.roe_history[-1] == pytest.approx(150000000 / 1100000000)


def test_edinet_xbrl_quarterly_duration_skipped():
    extra = """
  <xbrli:context id="CurrentYTDDuration">
    <xbrli:entity><xbrli:identifier scheme="http://disclosure.edinet-fsa.go.jp">E00000</xbrli:identifier></xbrli:entity>
    <xbrli:period><xbrli:startDate>2025-10-01</xbrli:startDate><xbrli:endDate>2025-12-31</xbrli:endDate></xbrli:period>
  </xbrli:context>
  <jpigp:ProfitLossAttributableToOwnersOfParentIFRS contextRef="CurrentYTDDuration" unitRef="JPY" decimals="0">999999999</jpigp:ProfitLossAttributableToOwnersOfParentIFRS>
"""
    xml = make_ifrs_xbrl(TOYOTA_ROWS[:2], extra=extra)
    fundamentals = parse_edinet_instance_xml(xml)
    assert fundamentals.roe_history is not None
    assert len(fundamentals.roe_history) == 1
    assert fundamentals.latest_roe == pytest.approx(3_848_098_000_000.0 / 35_924_826_000_000.0)


def test_edinet_xbrl_usd_equity_rejected():
    xml = make_ifrs_xbrl(TOYOTA_ROWS[:1]).replace("iso4217:JPY", "iso4217:USD").replace('unitRef="JPY"', 'unitRef="USD"')
    xml = xml.replace('<xbrli:unit id="JPY">', '<xbrli:unit id="USD">')
    fundamentals = parse_edinet_instance_xml(xml)
    assert fundamentals.book_value is None


def test_edinet_xbrl_missing_treasury_leaves_shares_missing():
    xml = make_ifrs_xbrl(TOYOTA_ROWS[:1])
    xml = xml.replace(
        '<jpdei:NumberOfTreasuryStockAtTheEndOfFiscalYearDEI contextRef="CurrentYearInstant" unitRef="Shares" decimals="0">0</jpdei:NumberOfTreasuryStockAtTheEndOfFiscalYearDEI>',
        "",
    )
    fundamentals = parse_edinet_instance_xml(xml)
    assert fundamentals.shares_outstanding is None
    assert fundamentals.book_value == pytest.approx(39_918_854.0)


def test_edinet_xbrl_html_is_bot_wall():
    with pytest.raises(BotWallError):
        parse_edinet_instance_xml("<html>verify</html>")


def test_edinet_xbrl_zip_uses_publicdoc_not_auditdoc():
    public = make_ifrs_xbrl(TOYOTA_ROWS)
    audit = make_ifrs_xbrl(
        [("2026-03-31", "2025-04-01", "1", "1", "1")]
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr("XBRL/AuditDoc/junk.xbrl", audit)
        zf.writestr("XBRL/PublicDoc/jpcrp030000-asr-001.xbrl", public)
    fundamentals = parse_edinet_xbrl_zip(buffer.getvalue())
    assert fundamentals.book_value == pytest.approx(39_918_854.0)


def test_fetch_edinet_xbrl_requires_key_without_fetcher():
    with pytest.raises(FetchError, match="EDINET_API_KEY"):
        fetch_edinet_xbrl_zip("S100AAAA", api_key="")


def test_fetch_edinet_xbrl_does_not_hit_network_when_injected():
    public = make_ifrs_xbrl(TOYOTA_ROWS)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr("XBRL/PublicDoc/instance.xbrl", public)

    def fake_fetch(url: str) -> tuple[int, str, bytes]:
        assert "S100AAAA" in url
        assert "type=1" in url
        assert "Subscription-Key" not in url
        return 200, "application/zip", buffer.getvalue()

    data = fetch_edinet_xbrl_zip("S100AAAA", fetcher=fake_fetch)
    fundamentals = parse_edinet_xbrl_zip(data)
    assert fundamentals.book_value == pytest.approx(39_918_854.0)


def test_fetch_edinet_xbrl_401_is_fetch_error():
    def fake_fetch(url: str) -> tuple[int, str, bytes]:
        return 401, "application/json", b'{"message":"denied"}'

    with pytest.raises(FetchError, match="401"):
        fetch_edinet_xbrl_zip("S100AAAA", fetcher=fake_fetch)


def test_edinet_xbrl_url_redacts_key():
    url = edinet_xbrl_url("S100AAAA", api_key="secret")
    assert "secret" in url
    assert "secret" not in redact_url(url)


def test_edinet_snapshot_ranks_with_recorded_files(tmp_path: Path):
    snapshot = load_edinet_snapshot(
        raw_dir=YAHOO_DIR,
        edinet_dir=XBRL_DIR,
        fundamentals_path=tmp_path / "empty.json",
    )
    assert snapshot.source == "edinet"
    assert snapshot.fundamentals_source == "edinet_xbrl"
    computed = evaluate_universe(snapshot.stocks, snapshot.assumptions)
    by_ticker = {row["ticker"]: row for row in computed}
    toyota = by_ticker["7203"]
    assert toyota["eligible"] is True
    assert toyota["rank"] is not None
    assert toyota["bookValue"] == pytest.approx(39_918_854.0)
    assert toyota["forecast"][9]["roe"] == toyota["costOfEquity"]
    assert by_ticker["6758"]["eligible"] is True
    assert by_ticker["6758"]["latestRoe"] < 0
    assert by_ticker["9984"]["eligible"] is True
    ranked = [row["ticker"] for row in computed if row["rank"] is not None]
    assert set(ranked) == {"7203", "6758", "9984"}


def test_edinet_without_xbrl_stays_ineligible(tmp_path: Path):
    snapshot = load_edinet_snapshot(
        raw_dir=YAHOO_DIR,
        edinet_dir=tmp_path,
        fundamentals_path=tmp_path / "empty.json",
    )
    computed = evaluate_universe(snapshot.stocks, snapshot.assumptions)
    toyota = next(row for row in computed if row["ticker"] == "7203")
    assert toyota["price"] == pytest.approx(3013.0)
    assert toyota["eligible"] is False
    assert "missing_book_value" in toyota["exclusionReasons"]
    assert toyota["bookValue"] is None
    assert snapshot.fundamentals_source == "missing"


def test_parse_edinet_xbrl_dir_merges_files(tmp_path: Path):
    first = make_ifrs_xbrl(TOYOTA_ROWS[2:])
    second = make_ifrs_xbrl(TOYOTA_ROWS[:2])
    (tmp_path / "older.xbrl").write_text(first, encoding="utf-8")
    (tmp_path / "newer.xbrl").write_text(second, encoding="utf-8")
    fundamentals = parse_edinet_xbrl_dir(tmp_path)
    assert fundamentals.roe_history is not None
    assert len(fundamentals.roe_history) == 3
    assert fundamentals.book_value == pytest.approx(39_918_854.0)
