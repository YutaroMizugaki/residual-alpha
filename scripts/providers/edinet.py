"""EDINET API v2 document list. XBRL instances are parsed separately."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from providers.errors import BotWallError, FetchError, InvalidPriceDataError


YUHO_TYPE = "120"


@dataclass(frozen=True)
class EdinetDocument:
    doc_id: str
    sec_code: str | None
    filer_name: str | None
    doc_type_code: str | None
    period_end: str | None
    xbrl_flag: str | None


def _normalize_sec_code(value: str) -> str:
    text = value.strip().strip("'\"")
    if len(text) == 4 and text.isdigit():
        return text + "0"
    return text


def parse_edinet_documents(payload: Any) -> list[EdinetDocument]:
    if isinstance(payload, str):
        text = payload.lstrip()
        if text.startswith("<!") or text.startswith("<html"):
            raise BotWallError("EDINET returned HTML instead of JSON")
        try:
            payload = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise FetchError("EDINET payload is not JSON") from exc
    if not isinstance(payload, dict):
        raise InvalidPriceDataError("EDINET payload is not an object")

    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    status = str((metadata.get("status") if metadata else None) or payload.get("status") or "")
    if status in {"401", "403"}:
        raise FetchError(f"EDINET HTTP {status}")

    results = payload.get("results")
    if results is None:
        raise FetchError("EDINET results are missing")
    if not isinstance(results, list):
        raise InvalidPriceDataError("EDINET results are invalid")

    documents: list[EdinetDocument] = []
    for row in results:
        if not isinstance(row, dict):
            continue
        doc_id = row.get("docID")
        if not doc_id:
            continue
        sec = row.get("secCode")
        sec_code = None if sec in (None, "") else _normalize_sec_code(str(sec))
        doc_type = row.get("docTypeCode")
        if isinstance(doc_type, str):
            doc_type = doc_type.strip().strip("'\"")
        documents.append(
            EdinetDocument(
                doc_id=str(doc_id),
                sec_code=sec_code,
                filer_name=None if row.get("filerName") in (None, "") else str(row.get("filerName")),
                doc_type_code=None if doc_type in (None, "") else str(doc_type),
                period_end=None if row.get("periodEnd") in (None, "") else str(row.get("periodEnd")),
                xbrl_flag=None if row.get("xbrlFlag") in (None, "") else str(row.get("xbrlFlag")),
            )
        )
    return documents


def latest_yuho(documents: list[EdinetDocument], sec_code: str) -> EdinetDocument | None:
    wanted = _normalize_sec_code(sec_code)
    matches = [
        doc
        for doc in documents
        if doc.sec_code == wanted and doc.doc_type_code == YUHO_TYPE
    ]
    if not matches:
        return None
    matches.sort(key=lambda doc: (doc.period_end or "", doc.doc_id))
    return matches[-1]


def yuho_history(
    documents: list[EdinetDocument],
    sec_code: str,
    *,
    limit: int = 5,
) -> list[EdinetDocument]:
    """Latest unique fiscal-year-end yuho filings that advertise XBRL."""
    wanted = _normalize_sec_code(sec_code)
    matches = [
        doc
        for doc in documents
        if doc.sec_code == wanted
        and doc.doc_type_code == YUHO_TYPE
        and doc.xbrl_flag != "0"
    ]
    by_period: dict[str, EdinetDocument] = {}
    for doc in sorted(matches, key=lambda item: (item.period_end or "", item.doc_id)):
        if doc.period_end:
            by_period[doc.period_end] = doc
    ordered = sorted(by_period.values(), key=lambda item: item.period_end or "", reverse=True)
    return ordered[:limit]
