import { formatScore } from "@/lib/format";

export function ScoreBreakdown({
  valuationScore,
  qualityScore,
  riskScore,
  totalScore,
}: {
  valuationScore: number | null;
  qualityScore: number | null;
  riskScore: number | null;
  totalScore: number | null;
}) {
  const rows = [
    { label: "Valuation", score: valuationScore, max: 50, color: "bg-sky-700" },
    { label: "Quality", score: qualityScore, max: 30, color: "bg-emerald-700" },
    { label: "Risk", score: riskScore, max: 20, color: "bg-amber-700" },
  ];

  if (
    valuationScore === null &&
    qualityScore === null &&
    riskScore === null &&
    totalScore === null
  ) {
    return (
      <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
        <h2 className="text-sm font-semibold tracking-wide text-slate-700 uppercase">
          Score breakdown
        </h2>
        <p className="mt-2 text-sm text-slate-600">
          Score is unavailable. Missing inputs are not treated as zero points.
        </p>
      </div>
    );
  }

  return (
    <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
      <div className="mb-4 flex items-baseline justify-between">
        <h2 className="text-sm font-semibold tracking-wide text-slate-700 uppercase">
          Score breakdown
        </h2>
        <p className="font-mono text-2xl tabular-nums">{formatScore(totalScore)}</p>
      </div>
      <ul className="space-y-3">
        {rows.map((row) => {
          const width =
            row.score === null ? 0 : Math.max(0, Math.min(100, (row.score / row.max) * 100));
          return (
            <li key={row.label}>
              <div className="mb-1 flex justify-between text-sm">
                <span>
                  {row.label}{" "}
                  <span className="text-slate-500">/ {row.max}</span>
                </span>
                <span className="font-mono tabular-nums">{formatScore(row.score)}</span>
              </div>
              <div className="h-2 overflow-hidden rounded bg-slate-100">
                <div className={`h-full ${row.color}`} style={{ width: `${width}%` }} />
              </div>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
