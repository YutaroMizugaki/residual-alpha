import Link from "next/link";
import { notFound } from "next/navigation";

import { MetricCard } from "@/components/metric-card";
import { ScoreBreakdown } from "@/components/score-breakdown";
import { SourceKicker } from "@/components/source-kicker";
import { loadMeta, loadRankings, loadStock } from "@/lib/data";
import {
  formatBeta,
  formatNumber,
  formatPercent,
  formatPrice,
  formatScore,
} from "@/lib/format";

type PageProps = {
  params: Promise<{ ticker: string }>;
};

export async function generateStaticParams() {
  const rows = await loadRankings();
  return rows.map((row) => ({ ticker: row.ticker }));
}

export async function generateMetadata({ params }: PageProps) {
  const { ticker } = await params;
  const stock = await loadStock(ticker);
  if (!stock) {
    return { title: "Not found — Residual Alpha" };
  }
  return {
    title: `${stock.ticker} ${stock.companyName} — Residual Alpha`,
  };
}

export default async function StockPage({ params }: PageProps) {
  const { ticker } = await params;
  const [stock, meta] = await Promise.all([loadStock(ticker), loadMeta()]);
  if (!stock) {
    notFound();
  }

  const upsideClass =
    stock.intrinsicUpside === null
      ? ""
      : stock.intrinsicUpside >= 0
        ? "text-emerald-700"
        : "text-red-700";
  const isFixture = meta.source === "fixture";

  return (
    <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-8">
      <SourceKicker meta={meta} />
      <p className="mt-2 text-sm">
        <Link href="/ranking" className="underline">
          ← Ranking
        </Link>
      </p>
      <h1 className="mt-2 text-2xl font-semibold">
        <span className="font-mono">{stock.ticker}</span> {stock.companyName}
      </h1>
      <p className="mt-1 text-sm text-slate-600">
        Price source {stock.priceSource ?? "missing"}
        {stock.priceAsOf ? ` as of ${stock.priceAsOf}` : ""}. Fundamentals
        source {stock.fundamentalsSource ?? "missing"}
        {stock.fundamentalsAsOf ? ` (FY ${stock.fundamentalsAsOf})` : ""}.
        Book value is million JPY; shares are million shares; displayed price
        is JPY per share.
        {isFixture
          ? " Fictional test issuer."
          : " Real listed ticker. Not investment advice."}
      </p>

      {!stock.eligible ? (
        <div className="mt-4 rounded-md border border-amber-300 bg-amber-50 p-3 text-sm">
          <p className="font-medium">Not eligible for ranking</p>
          <p className="mt-1 text-slate-700">
            {stock.exclusionReasons.join(", ") || "missing inputs"}
          </p>
        </div>
      ) : null}

      <div className="mt-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <MetricCard
          label="Price"
          value={formatPrice(stock.price)}
          hint={
            [stock.priceAsOf ? `as of ${stock.priceAsOf}` : null, stock.priceSource]
              .filter(Boolean)
              .join(" · ") || undefined
          }
        />
        <MetricCard
          label="Intrinsic Price"
          value={formatPrice(stock.intrinsicPrice)}
        />
        <MetricCard
          label="Intrinsic Upside"
          value={formatPercent(stock.intrinsicUpside, { signed: true })}
          hint="Intrinsic Price / Price − 1"
        />
        <MetricCard label="Total Score" value={formatScore(stock.totalScore)} />
        <MetricCard
          label="Beta (raw / adj)"
          value={`${formatBeta(stock.betaRaw)} / ${formatBeta(stock.betaAdjusted)}`}
          hint={[stock.betaStatus, stock.returnCount != null ? `${stock.returnCount} aligned returns` : null]
            .filter(Boolean)
            .join(" · ")}
        />
        <MetricCard
          label="Cost of Equity"
          value={formatPercent(stock.costOfEquity)}
          hint={`rf ${formatPercent(stock.riskFreeRate)} + β × ERP ${formatPercent(stock.equityRiskPremium)}`}
        />
        <MetricCard
          label="Normalized ROE"
          value={formatPercent(stock.normalizedRoe)}
          hint={`latest ${formatPercent(stock.latestRoe)} · ${stock.normalizedRoeStatus}`}
        />
        <MetricCard
          label="Excess ROE"
          value={formatPercent(stock.excessRoe, { signed: true })}
        />
        <MetricCard
          label="Book Value"
          value={formatNumber(stock.bookValue, 0)}
          hint={
            [
              "million JPY",
              stock.fundamentalsAsOf ? `FY ${stock.fundamentalsAsOf}` : null,
              stock.fundamentalsSource,
            ]
              .filter(Boolean)
              .join(" · ")
          }
        />
        <MetricCard
          label="Shares"
          value={formatNumber(stock.sharesOutstanding, 0)}
          hint="million shares"
        />
        <MetricCard
          label="Intrinsic Equity Value"
          value={formatNumber(stock.intrinsicEquityValue, 0)}
          hint="million JPY"
        />
      </div>

      <div className="mt-6">
        <ScoreBreakdown
          valuationScore={stock.valuationScore}
          qualityScore={stock.qualityScore}
          riskScore={stock.riskScore}
          totalScore={stock.totalScore}
        />
      </div>

      <section className="mt-8">
        <h2 className="text-sm font-semibold tracking-wide text-slate-700 uppercase">
          Residual income forecast
        </h2>
        {stock.forecast.length === 0 ? (
          <p className="mt-2 text-sm text-slate-600">
            Forecast is unavailable because required inputs are missing. Missing
            values are not treated as zero.
          </p>
        ) : (
          <div className="mt-3 overflow-x-auto rounded-lg border border-slate-200 bg-white">
            <table className="min-w-full text-left text-sm">
              <thead className="bg-slate-50 text-xs tracking-wide text-slate-600 uppercase">
                <tr>
                  <th className="px-3 py-2">Year</th>
                  <th className="px-3 py-2 text-right">Begin BV</th>
                  <th className="px-3 py-2 text-right">ROE</th>
                  <th className="px-3 py-2 text-right">Net Income</th>
                  <th className="px-3 py-2 text-right">Equity Charge</th>
                  <th className="px-3 py-2 text-right">RI</th>
                  <th className="px-3 py-2 text-right">DF</th>
                  <th className="px-3 py-2 text-right">PV(RI)</th>
                  <th className="px-3 py-2 text-right">Dividend</th>
                  <th className="px-3 py-2 text-right">End BV</th>
                </tr>
              </thead>
              <tbody>
                {stock.forecast.map((year) => (
                  <tr key={year.year} className="border-t border-slate-100">
                    <td className="px-3 py-2 font-mono">{year.year}</td>
                    <td className="px-3 py-2 text-right font-mono tabular-nums">
                      {formatNumber(year.beginningBookValue, 1)}
                    </td>
                    <td className="px-3 py-2 text-right font-mono tabular-nums">
                      {formatPercent(year.roe)}
                    </td>
                    <td className="px-3 py-2 text-right font-mono tabular-nums">
                      {formatNumber(year.netIncome, 1)}
                    </td>
                    <td className="px-3 py-2 text-right font-mono tabular-nums">
                      {formatNumber(year.equityCharge, 1)}
                    </td>
                    <td className="px-3 py-2 text-right font-mono tabular-nums">
                      {formatNumber(year.residualIncome, 1)}
                    </td>
                    <td className="px-3 py-2 text-right font-mono tabular-nums">
                      {formatNumber(year.discountFactor, 4)}
                    </td>
                    <td className="px-3 py-2 text-right font-mono tabular-nums">
                      {formatNumber(year.pvResidualIncome, 1)}
                    </td>
                    <td className="px-3 py-2 text-right font-mono tabular-nums">
                      {formatNumber(year.dividend, 1)}
                    </td>
                    <td className="px-3 py-2 text-right font-mono tabular-nums">
                      {formatNumber(year.endingBookValue, 1)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <p className={`mt-3 text-sm ${upsideClass}`}>
          Upside {formatPercent(stock.intrinsicUpside, { signed: true })}
        </p>
      </section>
    </main>
  );
}
