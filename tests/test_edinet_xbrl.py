from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest

from models.pipeline import evaluate_universe
from providers.edinet_xbrl import (
    compact_edinet_xbrl_dir,
    context_is_breakdown,
    parse_edinet_instance_xml,
    parse_edinet_xbrl_dir,
    parse_edinet_xbrl_zip,
)
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


def test_edinet_xbrl_missing_treasury_defaults_to_zero_shares():
    xml = make_ifrs_xbrl(TOYOTA_ROWS[:1])
    xml = xml.replace(
        '<jpdei:NumberOfTreasuryStockAtTheEndOfFiscalYearDEI contextRef="CurrentYearInstant" unitRef="Shares" decimals="0">0</jpdei:NumberOfTreasuryStockAtTheEndOfFiscalYearDEI>',
        "",
    )
    fundamentals = parse_edinet_instance_xml(xml)
    assert fundamentals.shares_outstanding == pytest.approx(13_033.384474)
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
    assert set(ranked) == {
        "7203",
        "6758",
        "9984",
        "6861",
        "6501",
        "8035",
        "4063",
        "8306",
        "9432",
        "6098",
        "4568",
        "6503",
        "6857",
        "7267",
        "8001",
        "8058",
        "8316",
        "8766",
        "9434",
        "7974",
        "9983",
        "3382",
        "2914",
        "8729",
    }
    assert toyota["fundamentalsSource"] == "edinet_xbrl"
    assert toyota["priceSource"] == "yahoo_chart"
    assert by_ticker["6861"]["eligible"] is True
    assert by_ticker["6861"]["price"] is not None
    assert by_ticker["6861"]["price"] != 0
    assert by_ticker["6861"]["bookValue"] == pytest.approx(3_413_911.0)
    assert by_ticker["6861"]["fundamentalsAsOf"] == "2026-03-20"
    assert by_ticker["6861"]["priceSource"] == "yahoo_chart"
    assert by_ticker["6861"]["fundamentalsSource"] == "edinet_xbrl"
    assert by_ticker["7267"]["eligible"] is True
    assert by_ticker["7267"]["latestRoe"] < 0
    assert by_ticker["7974"]["eligible"] is True
    assert by_ticker["7974"]["fundamentalsSource"] == "edinet_xbrl"
    assert by_ticker["8766"]["eligible"] is True
    assert by_ticker["8766"]["fundamentalsSource"] == "edinet_xbrl"
    assert by_ticker["9983"]["eligible"] is True
    assert by_ticker["9983"]["fundamentalsSource"] == "edinet_xbrl"
    assert by_ticker["2914"]["eligible"] is True
    assert by_ticker["2914"]["fundamentalsSource"] == "edinet_xbrl"
    assert by_ticker["2914"]["roeCount"] == 3
    assert by_ticker["2914"]["bookValue"] is not None
    assert by_ticker["8001"]["eligible"] is True


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
    assert toyota["fundamentalsSource"] is None


def test_parse_edinet_xbrl_dir_merges_files(tmp_path: Path):
    first = make_ifrs_xbrl(TOYOTA_ROWS[2:])
    second = make_ifrs_xbrl(TOYOTA_ROWS[:2])
    (tmp_path / "older.xbrl").write_text(first, encoding="utf-8")
    (tmp_path / "newer.xbrl").write_text(second, encoding="utf-8")
    fundamentals = parse_edinet_xbrl_dir(tmp_path)
    assert fundamentals.roe_history is not None
    assert len(fundamentals.roe_history) == 3
    assert fundamentals.book_value == pytest.approx(39_918_854.0)


def test_parse_edinet_xbrl_dir_keeps_current_year_over_later_comparative(tmp_path: Path):
    older = make_ifrs_xbrl(
        [
            ("2024-03-31", "2023-04-01", "2758058000000", "369642000000", "243207000"),
            ("2023-03-31", "2022-04-01", "2461196000000", "362963000000", "243207000"),
        ]
    )
    newer = make_ifrs_xbrl(
        [
            ("2026-03-31", "2025-04-01", "3413911000000", "445185000000", "243207684"),
            ("2025-03-31", "2024-04-01", "3077874000000", "398656000000", "243207000"),
        ],
        extra="""
  <xbrli:context id="Prior2YearInstant">
    <xbrli:entity><xbrli:identifier scheme="http://disclosure.edinet-fsa.go.jp">E00000</xbrli:identifier></xbrli:entity>
    <xbrli:period><xbrli:instant>2024-03-31</xbrli:instant></xbrli:period>
  </xbrli:context>
  <jpigp:NetAssets contextRef="Prior2YearInstant" unitRef="JPY" decimals="-6">1</jpigp:NetAssets>
""",
    )
    (tmp_path / "older.xbrl").write_text(older, encoding="utf-8")
    (tmp_path / "newer.xbrl").write_text(newer, encoding="utf-8")
    fundamentals = parse_edinet_xbrl_dir(tmp_path)
    assert fundamentals.book_value == pytest.approx(3_413_911.0)
    assert fundamentals.roe_history is not None
    assert len(fundamentals.roe_history) == 3
    assert fundamentals.roe_history[0] == pytest.approx(369_642_000_000 / 2_461_196_000_000)
    assert fundamentals.roe_history[1] == pytest.approx(398_656_000_000 / 2_758_058_000_000)
    assert fundamentals.latest_roe == pytest.approx(445_185_000_000 / 3_077_874_000_000)


def test_context_is_breakdown_skips_line_items_not_consolidation():
    assert context_is_breakdown("CurrentYearInstant") is False
    assert context_is_breakdown("CurrentYearInstant_NonConsolidatedMember") is False
    assert context_is_breakdown("Prior2YearInstant_CapitalStockMember") is True
    assert context_is_breakdown("CurrentYearInstant_Row1Member") is True
    assert context_is_breakdown("Prior2YearInstant_NonConsolidatedMember_CapitalStockMember") is True


def test_edinet_xbrl_ignores_capital_stock_member_net_assets():
    extra = """
  <xbrli:context id="CurrentYearInstant_CapitalStockMember">
    <xbrli:entity><xbrli:identifier scheme="http://disclosure.edinet-fsa.go.jp">E00000</xbrli:identifier></xbrli:entity>
    <xbrli:period><xbrli:instant>2026-03-31</xbrli:instant></xbrli:period>
  </xbrli:context>
  <jpigp:NetAssets contextRef="CurrentYearInstant_CapitalStockMember" unitRef="JPY" decimals="-6">1</jpigp:NetAssets>
"""
    xml = make_ifrs_xbrl(TOYOTA_ROWS, extra=extra)
    fundamentals = parse_edinet_instance_xml(xml)
    assert fundamentals.book_value == pytest.approx(39_918_854.0)
    assert fundamentals.latest_roe == pytest.approx(3_848_098_000_000.0 / 35_924_826_000_000.0)


def test_edinet_xbrl_treasury_shares_etc_counts_as_treasury():
    xml = make_ifrs_xbrl(TOYOTA_ROWS[:1])
    xml = xml.replace(
        '<jpdei:NumberOfTreasuryStockAtTheEndOfFiscalYearDEI contextRef="CurrentYearInstant" unitRef="Shares" decimals="0">0</jpdei:NumberOfTreasuryStockAtTheEndOfFiscalYearDEI>',
        '<jpcrp:TotalNumberOfSharesHeldTreasurySharesEtc contextRef="CurrentYearInstant" unitRef="Shares" decimals="0">1000000</jpcrp:TotalNumberOfSharesHeldTreasurySharesEtc>',
    )
    xml = xml.replace(
        "xmlns:jpdei=",
        'xmlns:jpcrp="http://disclosure.edinet-fsa.go.jp/taxonomy/jpcrp/2025-11-01/jpcrp_cor" xmlns:jpdei=',
    )
    fundamentals = parse_edinet_instance_xml(xml)
    assert fundamentals.shares_outstanding == pytest.approx((13_033_384_474 - 1_000_000) / 1_000_000)


def test_edinet_xbrl_filing_date_issued_shares_map_to_current_year():
    xml = make_ifrs_xbrl(TOYOTA_ROWS[:1])
    xml = xml.replace(
        '<jpdei:NumberOfIssuedAndOutstandingSharesAtTheEndOfFiscalYearIncludingTreasuryStockDEI contextRef="CurrentYearInstant" unitRef="Shares" decimals="0">13033384474</jpdei:NumberOfIssuedAndOutstandingSharesAtTheEndOfFiscalYearIncludingTreasuryStockDEI>',
        """  <xbrli:context id="FilingDateInstant">
    <xbrli:entity><xbrli:identifier scheme="http://disclosure.edinet-fsa.go.jp">E00000</xbrli:identifier></xbrli:entity>
    <xbrli:period><xbrli:instant>2026-06-15</xbrli:instant></xbrli:period>
  </xbrli:context>
  <jpcrp:NumberOfIssuedSharesAsOfFiscalYearEndIssuedSharesTotalNumberOfSharesEtc contextRef="FilingDateInstant" unitRef="Shares" decimals="0">13033384474</jpcrp:NumberOfIssuedSharesAsOfFiscalYearEndIssuedSharesTotalNumberOfSharesEtc>""",
    )
    xml = xml.replace(
        "xmlns:jpdei=",
        'xmlns:jpcrp="http://disclosure.edinet-fsa.go.jp/taxonomy/jpcrp/2025-11-01/jpcrp_cor" xmlns:jpdei=',
    )
    fundamentals = parse_edinet_instance_xml(xml)
    assert fundamentals.shares_outstanding == pytest.approx(13_033.384474)
    assert fundamentals.fiscal_year_end == "2026-03-31"


def test_compact_edinet_roundtrips_toyota_fixture():
    xml = compact_edinet_xbrl_dir(XBRL_DIR / "72030")
    original = parse_edinet_xbrl_dir(XBRL_DIR / "72030")
    compact = parse_edinet_instance_xml(xml)
    assert compact.book_value == pytest.approx(original.book_value)
    assert compact.shares_outstanding == pytest.approx(original.shares_outstanding)
    assert compact.roe_history == original.roe_history
    assert "PublicDoc" not in xml
    assert "CapitalStockMember" not in xml


def test_compact_edinet_dir_universe_only(tmp_path: Path):
    from compact_edinet_xbrl import compact_edinet_universe

    src = tmp_path / "src"
    dst = tmp_path / "dst"
    (src / "noise").mkdir(parents=True)
    (src / "noise" / "junk.xbrl").write_text("<not-xbrl>", encoding="utf-8")
    (src / "72030").mkdir()
    (src / "72030" / "instance.xbrl").write_text(make_ifrs_xbrl(TOYOTA_ROWS), encoding="utf-8")
    universe = {
        "marketSymbol": "^N225",
        "stocks": [
            {
                "ticker": "7203",
                "yahooSymbol": "7203.T",
                "edinetSecCode": "72030",
                "companyName": "Toyota",
            }
        ],
    }
    assert compact_edinet_universe(src, dst, universe=universe) == 0
    assert not (dst / "noise").exists()
    written = (dst / "72030" / "instance.xbrl").read_text(encoding="utf-8")
    fundamentals = parse_edinet_instance_xml(written)
    assert fundamentals.book_value == pytest.approx(39_918_854.0)
    extra = {
        "marketSymbol": "^N225",
        "stocks": universe["stocks"]
        + [
            {
                "ticker": "6861",
                "yahooSymbol": "6861.T",
                "edinetSecCode": "68610",
                "companyName": "Keyence",
            }
        ],
    }
    missing = compact_edinet_universe(src, dst, universe=extra)
    assert missing == 1
    existing_only = compact_edinet_universe(src, dst, universe=extra, existing_only=True)
    assert existing_only == 0
    assert (dst / "72030" / "instance.xbrl").exists()
    assert not (dst / "68610" / "instance.xbrl").exists()
    poison = tmp_path / "poison"
    (poison / "72030").mkdir(parents=True)
    (poison / "72030" / "instance.xbrl").write_text(make_ifrs_xbrl(TOYOTA_ROWS[:1]), encoding="utf-8")
    (poison / "68610").mkdir()
    (poison / "68610" / "instance.xbrl").write_text(
        (XBRL_DIR / "68610" / "instance.xbrl").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    keep_dst = tmp_path / "keep"
    (keep_dst / "72030").mkdir(parents=True)
    (keep_dst / "72030" / "instance.xbrl").write_text(written, encoding="utf-8")
    assert compact_edinet_universe(poison, keep_dst, universe=extra, keep_existing=True) == 0
    kept = parse_edinet_xbrl_dir(keep_dst / "72030")
    assert kept.book_value == pytest.approx(39_918_854.0)
    assert kept.roe_history is not None
    assert len(kept.roe_history) == 3
    added = parse_edinet_xbrl_dir(keep_dst / "68610")
    assert added.book_value == pytest.approx(3_413_911.0)
    already = compact_edinet_universe(poison, keep_dst, universe=extra, keep_existing=True)
    assert already == 0


def test_recorded_extra_edinet_is_complete():
    extras = [
        "68610",
        "65010",
        "80350",
        "40630",
        "83060",
        "94320",
        "60980",
        "45680",
        "65030",
        "68570",
        "72670",
        "80010",
        "80580",
        "83160",
        "87660",
        "94340",
        "99830",
    ]
    for code in extras:
        fundamentals = parse_edinet_xbrl_dir(XBRL_DIR / code)
        assert fundamentals.book_value is not None
        assert fundamentals.book_value != 0
        assert fundamentals.shares_outstanding is not None
        assert fundamentals.shares_outstanding != 0
        assert fundamentals.latest_roe is not None
        assert fundamentals.roe_history is not None
        assert len(fundamentals.roe_history) >= 3
        assert all(abs(value) < 2 for value in fundamentals.roe_history)
        assert fundamentals.fiscal_year_end in {
            "2026-03-31",
            "2026-03-20",
            "2025-03-31",
            "2025-08-31",
            "2025-12-31",
        }


def test_recorded_partial_edinet_is_not_padded():
    extras = [
        "45020",
        "63670",
        "70110",
        "77410",
        "80310",
        "84110",
        "94330",
    ]
    for code in extras:
        fundamentals = parse_edinet_xbrl_dir(XBRL_DIR / code)
        assert fundamentals.book_value is not None
        assert fundamentals.book_value != 0
        assert fundamentals.shares_outstanding is not None
        assert fundamentals.latest_roe is not None
        assert fundamentals.roe_history is not None
        assert len(fundamentals.roe_history) == 2
        assert all(abs(value) < 2 for value in fundamentals.roe_history)
