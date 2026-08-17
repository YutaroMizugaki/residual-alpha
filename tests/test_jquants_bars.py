from __future__ import annotations

import json
from pathlib import Path

import pytest

from models.pipeline import evaluate_universe
from providers.errors import BotWallError, FetchError, InvalidPriceDataError
from providers.http import (
    clamp_jquants_bars_window,
    default_fetcher,
    fetch_jquants_bars_json,
    jquants_bars_url,
    parse_jquants_subscription_window,
)
from providers.jquants_bars import compact_jquants_bars, parse_jquants_bars
from providers.loader import (
    JQUANTS_FREE_LAG_NOTE,
    JQUANTS_FREE_LAG_NOTE_JA,
    load_auto_snapshot,
    load_jquants_snapshot,
)

ROOT = Path(__file__).resolve().parents[1]
YAHOO_DIR = ROOT / "tests" / "data" / "yahoo"
JQUANTS_DIR = ROOT / "tests" / "data" / "jquants"
BARS_DIR = ROOT / "tests" / "data" / "jquants_bars"
FUND_DIR = ROOT / "tests" / "data" / "yahoo_fundamentals"
XBRL_DIR = ROOT / "tests" / "data" / "edinet_xbrl"


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _mini_universe(path: Path) -> Path:
    _write_json(
        path,
        {
            "priceSource": "yahoo_chart",
            "marketSymbol": "^N225",
            "marketName": "Nikkei 225",
            "range": "1y",
            "riskFreeRate": 0.015,
            "equityRiskPremium": 0.05,
            "retentionRatio": 0.5,
            "stocks": [
                {
                    "ticker": "7203",
                    "yahooSymbol": "7203.T",
                    "stooqSymbol": "7203.jp",
                    "jquantsCode": "72030",
                    "edinetSecCode": "72030",
                    "companyName": "Toyota Motor",
                }
            ],
        },
    )
    return path


def _poison_yahoo_chart(path: Path) -> None:
    _write_json(
        path,
        {
            "chart": {
                "result": [
                    {
                        "meta": {
                            "currency": "JPY",
                            "symbol": "7203.T",
                            "gmtoffset": 32400,
                        },
                        "timestamp": [1784246400, 1784592000, 1784678400],
                        "indicators": {"quote": [{"close": [1.0, 1.0, 1.0]}]},
                    }
                ],
                "error": None,
            }
        },
    )


def test_jquants_bars_toyota_adjc_matches_recorded_yahoo():
    payload = json.loads((BARS_DIR / "72030.json").read_text(encoding="utf-8"))
    series = parse_jquants_bars(payload, expected_code="72030")
    last = series.last()
    assert last is not None
    assert last[1] == pytest.approx(3013.0)
    assert series.currency == "JPY"


def test_jquants_bars_empty_adjc_is_missing_not_zero():
    payload = json.loads((BARS_DIR / "empty_adjc.json").read_text(encoding="utf-8"))
    series = parse_jquants_bars(payload, expected_code="72030")
    assert [point[1] for point in series.points] == [pytest.approx(3013.0)]
    assert 0 not in [point[1] for point in series.points]
    assert 100.0 not in [point[1] for point in series.points]


def test_jquants_bars_zero_adjc_is_invalid_not_price_zero():
    payload = json.loads((BARS_DIR / "zero_adjc.json").read_text(encoding="utf-8"))
    with pytest.raises(FetchError, match="no valid adjusted closes"):
        parse_jquants_bars(payload, expected_code="72030")


def test_jquants_bars_html_is_bot_wall():
    with pytest.raises(BotWallError):
        parse_jquants_bars("<html>verify</html>", expected_code="72030")


def test_jquants_bars_invalid_payload_shape():
    with pytest.raises(InvalidPriceDataError):
        parse_jquants_bars(["not", "an", "object"], expected_code="72030")


def test_jquants_bars_url_has_code_not_key():
    url = jquants_bars_url("72030", from_="2025-01-01", to="2026-01-01")
    assert "72030" in url
    assert "from=2025-01-01" in url
    assert "x-api-key" not in url


def test_fetch_jquants_bars_401_is_fetch_error():
    def fake_fetch(url: str) -> tuple[int, str, str]:
        return 401, "application/json", '{"message":"denied"}'

    with pytest.raises(FetchError, match="401"):
        fetch_jquants_bars_json("72030", fetcher=fake_fetch)


def test_parse_jquants_subscription_window():
    body = (
        '{"message": "Your subscription covers the following dates: '
        '2024-05-25 ~ 2026-05-25. If you want more data, please check other plans:'
        'https://jpx-jquants.com/#dataset"}'
    )
    assert parse_jquants_subscription_window(body) == ("2024-05-25", "2026-05-25")
    assert parse_jquants_subscription_window('{"message":"nope"}') is None


def test_clamp_jquants_bars_window_intersects_plan():
    assert clamp_jquants_bars_window(
        "2025-07-13", "2026-08-17", "2024-05-25", "2026-05-25"
    ) == ("2025-07-13", "2026-05-25")
    assert clamp_jquants_bars_window(
        None, None, "2024-05-25", "2026-05-25"
    ) == ("2024-05-25", "2026-05-25")


def test_fetch_jquants_bars_clamps_window_on_400():
    calls: list[str] = []

    def fake_fetch(url: str) -> tuple[int, str, str]:
        calls.append(url)
        if "to=2026-08-17" in url:
            return (
                400,
                "application/json",
                json.dumps(
                    {
                        "message": (
                            "Your subscription covers the following dates: "
                            "2024-05-25 ~ 2026-05-25. If you want more data, "
                            "please check other plans:https://jpx-jquants.com/#dataset"
                        )
                    }
                ),
            )
        assert "to=2026-05-25" in url
        assert "from=2025-07-13" in url
        return (
            200,
            "application/json",
            json.dumps({"data": [{"Date": "2026-05-25", "Code": "72030", "AdjC": 1.0}]}),
        )

    payload = fetch_jquants_bars_json(
        "72030", from_="2025-07-13", to="2026-08-17", fetcher=fake_fetch
    )
    assert len(calls) == 2
    assert payload["data"][0]["Date"] == "2026-05-25"


def test_fetch_jquants_bars_drops_window_when_400_has_no_coverage():
    calls: list[str] = []

    def fake_fetch(url: str) -> tuple[int, str, str]:
        calls.append(url)
        if "from=" in url or "to=" in url:
            return 400, "application/json", '{"message":"bad range"}'
        return (
            200,
            "application/json",
            json.dumps({"data": [{"Date": "2026-05-25", "Code": "72030", "AdjC": 1.0}]}),
        )

    payload = fetch_jquants_bars_json(
        "72030", from_="2025-07-13", to="2026-08-17", fetcher=fake_fetch
    )
    assert "from=" not in calls[-1]
    assert payload["data"][0]["AdjC"] == pytest.approx(1.0)


def test_default_fetcher_returns_http_error_status(monkeypatch: pytest.MonkeyPatch):
    import io
    from email.message import Message
    from urllib.error import HTTPError

    monkeypatch.setattr("providers.http.JQUANTS_MIN_INTERVAL_SEC", 0)
    monkeypatch.setattr("providers.http.JQUANTS_RATE_LIMIT_WAIT_SEC", 0)
    headers = Message()
    headers["Content-Type"] = "application/json"

    def fake_urlopen(request, timeout=20):
        raise HTTPError(
            request.full_url,
            400,
            "Bad Request",
            headers,
            io.BytesIO(
                b'{"message":"Your subscription covers the following dates: '
                b'2024-05-25 ~ 2026-05-25."}'
            ),
        )

    monkeypatch.setattr("providers.http.urlopen", fake_urlopen)
    status, content_type, body = default_fetcher(
        "https://api.jquants.com/v2/equities/bars/daily?code=72030"
    )
    assert status == 400
    assert "application/json" in content_type
    assert "2026-05-25" in body


def test_fetch_jquants_bars_paginates(tmp_path: Path):
    pages = {
        None: {
            "data": [{"Date": "2026-01-05", "Code": "72030", "AdjC": 100.0}],
            "pagination_key": "page-2",
        },
        "page-2": {
            "data": [{"Date": "2026-01-06", "Code": "72030", "AdjC": 110.0}],
        },
    }

    def fake_fetch(url: str) -> tuple[int, str, str]:
        key = "page-2" if "pagination_key=page-2" in url else None
        return 200, "application/json", json.dumps(pages[key])

    payload = fetch_jquants_bars_json("72030", fetcher=fake_fetch)
    assert len(payload["data"]) == 2
    series = parse_jquants_bars(payload, expected_code="72030")
    assert series.last()[1] == pytest.approx(110.0)


def test_jquants_snapshot_prefers_bars_over_yahoo(tmp_path: Path):
    yahoo_dir = tmp_path / "yahoo"
    _write_json(yahoo_dir / "_N225.json", json.loads((YAHOO_DIR / "_N225.json").read_text()))
    _poison_yahoo_chart(yahoo_dir / "7203.T.json")
    snapshot = load_jquants_snapshot(
        universe_path=_mini_universe(tmp_path / "universe.json"),
        raw_dir=yahoo_dir,
        jquants_dir=JQUANTS_DIR,
        jquants_bars_dir=BARS_DIR,
        fetch=False,
        fundamentals_path=tmp_path / "empty.json",
    )
    toyota = next(row for row in snapshot.stocks if row["ticker"] == "7203")
    assert snapshot.price_source == "jquants_bars"
    assert toyota["priceSource"] == "jquants_bars"
    assert toyota["price"] == pytest.approx(3013.0)
    assert toyota["price"] != pytest.approx(1.0)
    computed = evaluate_universe(snapshot.stocks, snapshot.assumptions)
    ranked = next(row for row in computed if row["ticker"] == "7203")
    assert ranked["eligible"] is True
    assert ranked["priceSource"] == "jquants_bars"
    meta = snapshot.meta()
    assert meta["priceLagNote"] == JQUANTS_FREE_LAG_NOTE
    assert "12 weeks" in meta["priceLagNote"]
    assert meta["priceLagNoteJa"] == JQUANTS_FREE_LAG_NOTE_JA


def test_jquants_snapshot_falls_back_to_yahoo_without_bars(tmp_path: Path):
    snapshot = load_jquants_snapshot(
        universe_path=_mini_universe(tmp_path / "universe.json"),
        raw_dir=YAHOO_DIR,
        jquants_dir=JQUANTS_DIR,
        jquants_bars_dir=tmp_path / "no-bars",
        fetch=False,
        fundamentals_path=tmp_path / "empty.json",
    )
    toyota = next(row for row in snapshot.stocks if row["ticker"] == "7203")
    assert snapshot.price_source == "yahoo_chart"
    assert toyota["priceSource"] == "yahoo_chart"
    assert toyota["price"] == pytest.approx(3013.0)
    assert snapshot.meta()["priceLagNote"] is None
    assert snapshot.meta()["priceLagNoteJa"] is None


def test_partial_jquants_bars_do_not_block_yahoo(tmp_path: Path):
    bars_dir = tmp_path / "bars"
    _write_json(
        bars_dir / "72030.json",
        {
            "data": [
                {"Date": "2026-01-05", "Code": "72030", "AdjC": 50.0},
                {"Date": "2026-01-06", "Code": "72030", "AdjC": 51.0},
            ]
        },
    )
    snapshot = load_jquants_snapshot(
        universe_path=_mini_universe(tmp_path / "universe.json"),
        raw_dir=YAHOO_DIR,
        jquants_dir=JQUANTS_DIR,
        jquants_bars_dir=bars_dir,
        fetch=False,
        fundamentals_path=tmp_path / "empty.json",
    )
    toyota = next(row for row in snapshot.stocks if row["ticker"] == "7203")
    assert snapshot.price_source == "yahoo_chart"
    assert toyota["priceSource"] == "yahoo_chart"
    assert toyota["price"] == pytest.approx(3013.0)
    assert toyota["price"] != pytest.approx(51.0)


def test_auto_prefers_jquants_bars_then_yahoo(tmp_path: Path):
    yahoo_dir = tmp_path / "yahoo"
    _write_json(yahoo_dir / "_N225.json", json.loads((YAHOO_DIR / "_N225.json").read_text()))
    _poison_yahoo_chart(yahoo_dir / "7203.T.json")
    snapshot = load_auto_snapshot(
        universe_path=_mini_universe(tmp_path / "universe.json"),
        raw_dir=yahoo_dir,
        fundamentals_dir=FUND_DIR,
        jquants_dir=JQUANTS_DIR,
        jquants_bars_dir=BARS_DIR,
        edinet_dir=XBRL_DIR,
        fundamentals_path=tmp_path / "empty.json",
    )
    toyota = next(row for row in snapshot.stocks if row["ticker"] == "7203")
    assert snapshot.price_source == "jquants_bars"
    assert toyota["price"] == pytest.approx(3013.0)
    assert toyota["bookValue"] == pytest.approx(39_918_854.0)


def test_auto_mixed_price_sources_across_names(tmp_path: Path):
    universe = tmp_path / "universe.json"
    _write_json(
        universe,
        {
            "priceSource": "yahoo_chart",
            "marketSymbol": "^N225",
            "range": "1y",
            "riskFreeRate": 0.015,
            "equityRiskPremium": 0.05,
            "retentionRatio": 0.5,
            "stocks": [
                {
                    "ticker": "7203",
                    "yahooSymbol": "7203.T",
                    "jquantsCode": "72030",
                    "edinetSecCode": "72030",
                    "companyName": "Toyota Motor",
                },
                {
                    "ticker": "6758",
                    "yahooSymbol": "6758.T",
                    "jquantsCode": "67580",
                    "edinetSecCode": "67580",
                    "companyName": "Sony Group",
                },
            ],
        },
    )
    yahoo_dir = tmp_path / "yahoo"
    _write_json(yahoo_dir / "_N225.json", json.loads((YAHOO_DIR / "_N225.json").read_text()))
    _write_json(yahoo_dir / "6758.T.json", json.loads((YAHOO_DIR / "6758.T.json").read_text()))
    bars_dir = tmp_path / "bars"
    _write_json(bars_dir / "72030.json", json.loads((BARS_DIR / "72030.json").read_text()))
    snapshot = load_auto_snapshot(
        universe_path=universe,
        raw_dir=yahoo_dir,
        fundamentals_dir=FUND_DIR,
        jquants_dir=JQUANTS_DIR,
        jquants_bars_dir=bars_dir,
        edinet_dir=XBRL_DIR,
        fundamentals_path=tmp_path / "empty.json",
    )
    by_ticker = {row["ticker"]: row for row in snapshot.stocks}
    assert snapshot.price_source == "jquants_bars+yahoo_chart"
    assert snapshot.meta()["priceLagNote"] == JQUANTS_FREE_LAG_NOTE
    assert by_ticker["7203"]["price"] == pytest.approx(3013.0)
    assert by_ticker["7203"]["priceSource"] == "jquants_bars"
    assert by_ticker["6758"]["price"] == pytest.approx(3780.0)
    assert by_ticker["6758"]["priceSource"] == "yahoo_chart"


def test_auto_prefers_longer_yahoo_over_short_bars(tmp_path: Path):
    snapshot = load_auto_snapshot(
        universe_path=_mini_universe(tmp_path / "universe.json"),
        raw_dir=YAHOO_DIR,
        fundamentals_dir=FUND_DIR,
        jquants_dir=JQUANTS_DIR,
        jquants_bars_dir=BARS_DIR,
        edinet_dir=XBRL_DIR,
        fundamentals_path=tmp_path / "empty.json",
    )
    toyota = next(row for row in snapshot.stocks if row["ticker"] == "7203")
    assert toyota["priceSource"] == "yahoo_chart"
    assert toyota["price"] == pytest.approx(3013.0)
    computed = evaluate_universe(snapshot.stocks, snapshot.assumptions)
    ranked = next(row for row in computed if row["ticker"] == "7203")
    assert ranked["returnCount"] >= 199
    assert ranked["priceSource"] == "yahoo_chart"


def test_jquants_source_keeps_short_bars_when_yahoo_is_longer(tmp_path: Path):
    snapshot = load_jquants_snapshot(
        universe_path=_mini_universe(tmp_path / "universe.json"),
        raw_dir=YAHOO_DIR,
        jquants_dir=JQUANTS_DIR,
        jquants_bars_dir=BARS_DIR,
        fetch=False,
        fundamentals_path=tmp_path / "empty.json",
    )
    toyota = next(row for row in snapshot.stocks if row["ticker"] == "7203")
    assert snapshot.price_source == "jquants_bars"
    assert toyota["priceSource"] == "jquants_bars"
    assert toyota["price"] == pytest.approx(3013.0)
    computed = evaluate_universe(snapshot.stocks, snapshot.assumptions)
    ranked = next(row for row in computed if row["ticker"] == "7203")
    assert ranked["returnCount"] == 19
    assert ranked["priceSource"] == "jquants_bars"


def test_compact_jquants_bars_drops_ohlc_nulls_and_zero():
    payload = {
        "data": [
            {
                "Date": "2026-01-05",
                "Code": "72030",
                "O": 1,
                "H": 2,
                "L": 0.5,
                "C": 1,
                "AdjC": 10.0,
                "AdjFactor": 1.0,
            },
            {"Date": "2026-01-06", "Code": "72030", "C": 11.0, "AdjC": None},
            {"Date": "2026-01-07", "Code": "72030", "C": 12.0, "AdjC": ""},
            {"Date": "2026-01-08", "Code": "72030", "C": 0, "AdjC": 0},
            {"Date": "2026-01-09", "Code": "72030", "C": 13.0, "AdjC": 12.0},
        ]
    }
    compact = compact_jquants_bars(payload, expected_code="72030")
    rows = compact["data"]
    assert [row["Date"] for row in rows] == ["2026-01-05", "2026-01-09"]
    assert [row["AdjC"] for row in rows] == pytest.approx([10.0, 12.0])
    assert all(set(row) == {"Date", "Code", "AdjC"} for row in rows)
    series = parse_jquants_bars(compact, expected_code="72030")
    assert [price for _, price in series.points] == pytest.approx([10.0, 12.0])


def test_compact_jquants_bars_keeps_recorded_last_close():
    payload = json.loads((BARS_DIR / "72030.json").read_text(encoding="utf-8"))
    original = parse_jquants_bars(payload, expected_code="72030")
    compact = compact_jquants_bars(payload, expected_code="72030")
    compacted = parse_jquants_bars(compact, expected_code="72030")
    assert compacted.last() == original.last()
    assert compacted.last()[1] == pytest.approx(3013.0)
    assert len(compacted.points) == len(original.points)
    assert "O" not in compact["data"][0]
    assert "C" not in compact["data"][0]


def test_recorded_extra_jquants_bars_use_free_plan_window():
    extras = ["68610", "65010", "80350", "40630", "83060", "94320", "60980"]
    for code in extras:
        payload = json.loads((BARS_DIR / f"{code}.json").read_text(encoding="utf-8"))
        series = parse_jquants_bars(payload, expected_code=code)
        last = series.last()
        assert last is not None
        assert last[0].isoformat() == "2026-05-25"
        assert last[1] > 0
        assert 0 not in [point[1] for point in series.points]
        assert len(series.points) == 208
        assert set(payload["data"][0]) == {"Date", "Code", "AdjC"}


def test_jquants_source_uses_extra_bars_without_filling_forward(tmp_path: Path):
    snapshot = load_jquants_snapshot(
        raw_dir=YAHOO_DIR,
        jquants_dir=JQUANTS_DIR,
        jquants_bars_dir=BARS_DIR,
        fetch=False,
        fundamentals_path=tmp_path / "empty.json",
    )
    keyence = next(row for row in snapshot.stocks if row["ticker"] == "6861")
    assert keyence["priceSource"] == "jquants_bars"
    assert keyence["price"] == pytest.approx(78860.0)
    assert keyence["priceAsOf"] == "2026-05-25"
    assert keyence["price"] != pytest.approx(86750.0)
    toyota = next(row for row in snapshot.stocks if row["ticker"] == "7203")
    assert toyota["price"] == pytest.approx(3013.0)
    assert toyota["priceAsOf"] == "2026-08-17"
    computed = evaluate_universe(snapshot.stocks, snapshot.assumptions)
    by_ticker = {row["ticker"]: row for row in computed}
    assert by_ticker["6861"]["eligible"] is False
    assert by_ticker["6861"]["roeCount"] == 1
    assert "insufficient_roe_history" in by_ticker["6861"]["exclusionReasons"]
    assert by_ticker["7203"]["eligible"] is True
    meta = snapshot.meta()
    assert meta["priceLagNote"] == JQUANTS_FREE_LAG_NOTE


def test_compact_jquants_bars_zero_only_is_missing():
    payload = json.loads((BARS_DIR / "zero_adjc.json").read_text(encoding="utf-8"))
    with pytest.raises(FetchError):
        compact_jquants_bars(payload, expected_code="72030")


def test_compact_jquants_dir_universe_only(tmp_path: Path):
    from compact_jquants_caches import compact_jquants_dir

    summaries_src = tmp_path / "src_summaries"
    bars_src = tmp_path / "src_bars"
    summaries_dst = tmp_path / "dst_summaries"
    bars_dst = tmp_path / "dst_bars"
    summaries_src.mkdir()
    bars_src.mkdir()
    (summaries_src / "noise.json").write_text('{"keep":true}\n', encoding="utf-8")
    (bars_src / "empty_adjc.json").write_text(
        (BARS_DIR / "empty_adjc.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (summaries_src / "72030.json").write_text(
        json.dumps(
            {
                "data": [
                    {
                        "DiscDate": "2026-05-08",
                        "DiscNo": "1",
                        "Code": "72030",
                        "DocType": "FYFinancialStatements_Consolidated_IFRS",
                        "CurPerType": "FY",
                        "CurPerEn": "2026-03-31",
                        "NP": "100",
                        "Eq": "1000",
                        "ShEq": "1000",
                        "ShOutFY": "100",
                        "TrShFY": "0",
                        "noise": "drop",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    (bars_src / "72030.json").write_text(
        json.dumps(
            {
                "data": [
                    {
                        "Date": "2026-01-05",
                        "Code": "72030",
                        "O": 9,
                        "C": 10,
                        "AdjC": 10.0,
                    },
                    {"Date": "2026-01-06", "Code": "72030", "C": 0, "AdjC": None},
                ]
            }
        ),
        encoding="utf-8",
    )
    universe = {
        "marketSymbol": "^N225",
        "stocks": [
            {
                "ticker": "7203",
                "yahooSymbol": "7203.T",
                "jquantsCode": "72030",
                "companyName": "Toyota",
            }
        ],
    }
    assert (
        compact_jquants_dir(
            summaries_src,
            bars_src,
            summaries_dst,
            bars_dst,
            universe=universe,
        )
        == 0
    )
    assert not (summaries_dst / "noise.json").exists()
    assert not (bars_dst / "empty_adjc.json").exists()
    bars = json.loads((bars_dst / "72030.json").read_text(encoding="utf-8"))
    assert bars["data"][0]["AdjC"] == pytest.approx(10.0)
    assert "O" not in bars["data"][0]
    summary = json.loads((summaries_dst / "72030.json").read_text(encoding="utf-8"))
    assert "noise" not in summary["data"][0]
    missing = compact_jquants_dir(
        tmp_path / "empty",
        bars_src,
        summaries_dst,
        bars_dst,
        universe=universe,
    )
    assert missing == 1
    extra = {
        "marketSymbol": "^N225",
        "stocks": universe["stocks"]
        + [
            {
                "ticker": "6861",
                "yahooSymbol": "6861.T",
                "jquantsCode": "68610",
                "companyName": "Keyence",
            }
        ],
    }
    existing_dst_s = tmp_path / "existing_summaries"
    existing_dst_b = tmp_path / "existing_bars"
    assert (
        compact_jquants_dir(
            summaries_src,
            bars_src,
            existing_dst_s,
            existing_dst_b,
            universe=extra,
            existing_only=True,
        )
        == 0
    )
    assert (existing_dst_s / "72030.json").exists()
    assert not (existing_dst_s / "68610.json").exists()
    assert not (existing_dst_b / "empty_adjc.json").exists()
    empty_only = compact_jquants_dir(
        tmp_path / "empty",
        tmp_path / "empty",
        existing_dst_s,
        existing_dst_b,
        universe=extra,
        existing_only=True,
    )
    assert empty_only == 1
    poison_summary = {
        "data": [
            {
                "DiscDate": "2020-05-01",
                "DiscNo": "poison",
                "Code": "72030",
                "DocType": "FYFinancialStatements_Consolidated_IFRS",
                "CurPerType": "FY",
                "CurPerEn": "2020-03-31",
                "NP": "1",
                "Eq": "1",
                "ShEq": "1",
                "ShOutFY": "1",
                "TrShFY": "0",
            }
        ]
    }
    poison_bars = {"data": [{"Date": "2020-01-05", "Code": "72030", "AdjC": 1.0}]}
    (summaries_src / "72030.json").write_text(json.dumps(poison_summary), encoding="utf-8")
    (bars_src / "72030.json").write_text(json.dumps(poison_bars), encoding="utf-8")
    (summaries_src / "68610.json").write_text(
        json.dumps(
            {
                "data": [
                    {
                        "DiscDate": "2026-05-08",
                        "DiscNo": "1",
                        "Code": "68610",
                        "DocType": "FYFinancialStatements_Consolidated_IFRS",
                        "CurPerType": "FY",
                        "CurPerEn": "2026-03-20",
                        "NP": "100",
                        "Eq": "1000",
                        "ShEq": "1000",
                        "ShOutFY": "100",
                        "TrShFY": "0",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    (bars_src / "68610.json").write_text(
        json.dumps({"data": [{"Date": "2026-05-25", "Code": "68610", "AdjC": 10.0}]}),
        encoding="utf-8",
    )
    keep_dst_s = tmp_path / "keep_summaries"
    keep_dst_b = tmp_path / "keep_bars"
    keep_dst_s.mkdir()
    keep_dst_b.mkdir()
    (keep_dst_s / "72030.json").write_text(
        (summaries_dst / "72030.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (keep_dst_b / "72030.json").write_text(
        (bars_dst / "72030.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    assert (
        compact_jquants_dir(
            summaries_src,
            bars_src,
            keep_dst_s,
            keep_dst_b,
            universe=extra,
            keep_existing=True,
        )
        == 0
    )
    kept = json.loads((keep_dst_s / "72030.json").read_text(encoding="utf-8"))
    assert kept["data"][0]["NP"] == "100"
    added = json.loads((keep_dst_s / "68610.json").read_text(encoding="utf-8"))
    assert added["data"][0]["Code"] == "68610"
    already = compact_jquants_dir(
        summaries_src,
        bars_src,
        keep_dst_s,
        keep_dst_b,
        universe=extra,
        keep_existing=True,
    )
    assert already == 0
