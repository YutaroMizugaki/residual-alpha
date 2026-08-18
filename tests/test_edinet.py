from __future__ import annotations

import json
from pathlib import Path

import pytest

from providers.edinet import latest_yuho, parse_edinet_documents, yuho_history
from providers.errors import BotWallError, FetchError
from fetch_edinet_list import fetch_edinet_lists, parse_filing_date
from providers.http import edinet_documents_url, fetch_edinet_documents_json

ROOT = Path(__file__).resolve().parents[1]
EDINET_DIR = ROOT / "tests" / "data" / "edinet"


def test_edinet_parses_yuho_and_strips_quoted_type():
    payload = json.loads((EDINET_DIR / "documents.json").read_text(encoding="utf-8"))
    documents = parse_edinet_documents(payload)
    toyota = latest_yuho(documents, "7203")
    assert toyota is not None
    assert toyota.doc_id == "S100AAAA"
    assert toyota.doc_type_code == "120"
    assert toyota.period_end == "2026-03-31"
    sony = latest_yuho(documents, "67580")
    assert sony is not None
    assert sony.doc_id == "S100CCCC"
    assert sony.doc_type_code == "120"


def test_edinet_yuho_history_unique_period_end():
    payload = json.loads((EDINET_DIR / "documents.json").read_text(encoding="utf-8"))
    documents = parse_edinet_documents(payload)
    toyota = yuho_history(documents, "7203")
    assert [doc.doc_id for doc in toyota] == ["S100AAAA"]
    sony = yuho_history(documents, "6758")
    assert [doc.doc_id for doc in sony] == ["S100CCCC"]
    jt = yuho_history(documents, "2914")
    assert [doc.doc_id for doc in jt] == ["S100IFRS"]
    assert jt[0].doc_type_code == "140"


def test_edinet_unauthorized_json_is_fetch_error():
    payload = json.loads((EDINET_DIR / "unauthorized.json").read_text(encoding="utf-8"))
    with pytest.raises(FetchError, match="401"):
        parse_edinet_documents(payload)


def test_edinet_html_is_bot_wall():
    with pytest.raises(BotWallError):
        parse_edinet_documents("<html>verify</html>")


def test_edinet_missing_results_not_empty_success():
    with pytest.raises(FetchError):
        parse_edinet_documents({"metadata": {"status": "200"}})


def test_fetch_edinet_requires_key_without_fetcher():
    with pytest.raises(FetchError, match="EDINET_API_KEY"):
        fetch_edinet_documents_json("2026-05-08", api_key="")


def test_fetch_edinet_does_not_hit_network_when_injected():
    def fake_fetch(url: str) -> tuple[int, str, str]:
        assert "documents.json" in url
        assert "2026-05-08" in url
        assert "Subscription-Key" not in url
        return 200, "application/json", (EDINET_DIR / "documents.json").read_text(encoding="utf-8")

    payload = fetch_edinet_documents_json("2026-05-08", fetcher=fake_fetch)
    documents = parse_edinet_documents(payload)
    assert latest_yuho(documents, "72030") is not None


def test_fetch_edinet_401_is_fetch_error():
    def fake_fetch(url: str) -> tuple[int, str, str]:
        return 401, "application/json", (EDINET_DIR / "unauthorized.json").read_text(encoding="utf-8")

    with pytest.raises(FetchError, match="401"):
        fetch_edinet_documents_json("2026-05-08", fetcher=fake_fetch)


def test_edinet_url_does_not_embed_key_until_live_fetch():
    url = edinet_documents_url("2026-01-01")
    assert "Subscription-Key" not in url
    keyed = edinet_documents_url("2026-01-01", api_key="secret")
    assert "secret" in keyed


def test_parse_filing_date_rejects_invalid():
    with pytest.raises(FetchError, match="invalid"):
        parse_filing_date("2026/06/22")


def test_fetch_edinet_lists_writes_operator_dates_only(tmp_path: Path):
    recorded = (EDINET_DIR / "documents.json").read_text(encoding="utf-8")
    seen: list[str] = []

    def fake_fetch(url: str) -> tuple[int, str, str]:
        assert "Subscription-Key" not in url
        seen.append(url)
        return 200, "application/json", recorded

    assert (
        fetch_edinet_lists(
            ["2026-06-15", "2026-06-15", " 2026-06-22 "],
            tmp_path,
            fetcher=fake_fetch,
        )
        == 0
    )
    assert (tmp_path / "2026-06-15.json").exists()
    assert (tmp_path / "2026-06-22.json").exists()
    assert len(seen) == 2
    assert "2026-06-15" in seen[0]
    assert "2026-06-22" in seen[1]
    assert not (tmp_path / "public").exists()


def test_fetch_edinet_lists_keeps_success_when_one_date_fails(tmp_path: Path):
    recorded = (EDINET_DIR / "documents.json").read_text(encoding="utf-8")

    def fake_fetch(url: str) -> tuple[int, str, str]:
        if "2026-06-16" in url:
            return 401, "application/json", (EDINET_DIR / "unauthorized.json").read_text(
                encoding="utf-8"
            )
        return 200, "application/json", recorded

    assert fetch_edinet_lists(["2026-06-15", "2026-06-16"], tmp_path, fetcher=fake_fetch) == 1
    assert (tmp_path / "2026-06-15.json").exists()
    assert not (tmp_path / "2026-06-16.json").exists()


def test_fetch_edinet_lists_empty_dates_fail(tmp_path: Path):
    assert fetch_edinet_lists([], tmp_path) == 1
    assert list(tmp_path.glob("*.json")) == []
