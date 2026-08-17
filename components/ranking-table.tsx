"use client";

import Link from "next/link";
import { useMemo, useState } from "react";

import {
  formatBeta,
  formatPercent,
  formatPrice,
  formatScore,
} from "@/lib/format";
import type { RankingRow } from "@/lib/types";

type SortKey = "totalScore" | "intrinsicUpside" | "betaAdjusted";

const SORT_LABELS: Record<SortKey, string> = {
  totalScore: "Total Score",
  intrinsicUpside: "Intrinsic Upside",
  betaAdjusted: "Beta",
};

function compareNullable(
  a: number | null,
  b: number | null,
  direction: "asc" | "desc",
): number {
  if (a === null && b === null) return 0;
  if (a === null) return 1;
  if (b === null) return -1;
  return direction === "asc" ? a - b : b - a;
}

export function RankingTable({ rows }: { rows: RankingRow[] }) {
  const [sortKey, setSortKey] = useState<SortKey>("totalScore");
  const [direction, setDirection] = useState<"asc" | "desc">("desc");

  const excluded = rows.filter((row) => !row.eligible);

  const sorted = useMemo(() => {
    const copy = rows.filter((row) => row.eligible);
    copy.sort((a, b) => compareNullable(a[sortKey], b[sortKey], direction));
    return copy;
  }, [rows, sortKey, direction]);

  function onSort(next: SortKey) {
    if (next === sortKey) {
      setDirection((current) => (current === "desc" ? "asc" : "desc"));
      return;
    }
    setSortKey(next);
    setDirection(next === "betaAdjusted" ? "asc" : "desc");
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-2">
        {(Object.keys(SORT_LABELS) as SortKey[]).map((key) => (
          <button
            key={key}
            type="button"
            onClick={() => onSort(key)}
            className={`rounded-full border px-3 py-1 text-sm ${
              sortKey === key
                ? "border-slate-900 bg-slate-900 text-white"
                : "border-slate-300 bg-white text-slate-700"
            }`}
          >
            Sort: {SORT_LABELS[key]}
            {sortKey === key ? (direction === "desc" ? " ↓" : " ↑") : ""}
          </button>
        ))}
      </div>

      <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white">
        <table className="min-w-full text-left text-sm">
          <thead className="bg-slate-50 text-xs tracking-wide text-slate-600 uppercase">
            <tr>
              <th className="px-3 py-2">Rank</th>
              <th className="px-3 py-2">Ticker</th>
              <th className="px-3 py-2">Company</th>
              <th className="px-3 py-2">Sources</th>
              <th className="px-3 py-2 text-right">Price</th>
              <th className="px-3 py-2 text-right">Intrinsic</th>
              <th className="px-3 py-2 text-right">Upside</th>
              <th className="px-3 py-2 text-right">Beta</th>
              <th className="px-3 py-2 text-right">Cost of Equity</th>
              <th className="px-3 py-2 text-right">ROE</th>
              <th className="px-3 py-2 text-right">Excess ROE</th>
              <th className="px-3 py-2 text-right">Valuation</th>
              <th className="px-3 py-2 text-right">Quality</th>
              <th className="px-3 py-2 text-right">Risk</th>
              <th className="px-3 py-2 text-right">Total</th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((row) => {
              const upsideClass =
                row.intrinsicUpside === null
                  ? ""
                  : row.intrinsicUpside >= 0
                    ? "text-emerald-700"
                    : "text-red-700";
              return (
                <tr key={row.ticker} className="border-t border-slate-100">
                  <td className="px-3 py-2 font-mono tabular-nums">{row.rank ?? "—"}</td>
                  <td className="px-3 py-2 font-mono">
                    <Link className="underline decoration-slate-300" href={`/stocks/${row.ticker}`}>
                      {row.ticker}
                    </Link>
                  </td>
                  <td className="px-3 py-2">{row.companyName}</td>
                  <td className="px-3 py-2 font-mono text-xs text-slate-600">
                    {row.priceSource ?? "missing"} / {row.fundamentalsSource ?? "missing"}
                  </td>
                  <td className="px-3 py-2 text-right font-mono tabular-nums">
                    {formatPrice(row.price)}
                  </td>
                  <td className="px-3 py-2 text-right font-mono tabular-nums">
                    {formatPrice(row.intrinsicPrice)}
                  </td>
                  <td className={`px-3 py-2 text-right font-mono tabular-nums ${upsideClass}`}>
                    {formatPercent(row.intrinsicUpside, { signed: true })}
                  </td>
                  <td className="px-3 py-2 text-right font-mono tabular-nums">
                    {formatBeta(row.betaAdjusted)}
                  </td>
                  <td className="px-3 py-2 text-right font-mono tabular-nums">
                    {formatPercent(row.costOfEquity)}
                  </td>
                  <td className="px-3 py-2 text-right font-mono tabular-nums">
                    {formatPercent(row.normalizedRoe)}
                  </td>
                  <td className="px-3 py-2 text-right font-mono tabular-nums">
                    {formatPercent(row.excessRoe, { signed: true })}
                  </td>
                  <td className="px-3 py-2 text-right font-mono tabular-nums">
                    {formatScore(row.valuationScore)}
                  </td>
                  <td className="px-3 py-2 text-right font-mono tabular-nums">
                    {formatScore(row.qualityScore)}
                  </td>
                  <td className="px-3 py-2 text-right font-mono tabular-nums">
                    {formatScore(row.riskScore)}
                  </td>
                  <td className="px-3 py-2 text-right font-mono font-semibold tabular-nums">
                    {formatScore(row.totalScore)}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {excluded.length > 0 ? (
        <p className="text-sm text-slate-500">
          Excluded from ranking ({excluded.length}):{" "}
          {excluded.map((row) => (
            <Link key={row.ticker} className="mr-2 underline" href={`/stocks/${row.ticker}`}>
              {row.ticker} {row.companyName} ({row.priceSource ?? "missing"} /{" "}
              {row.fundamentalsSource ?? "missing"})
            </Link>
          ))}
        </p>
      ) : null}
    </div>
  );
}
