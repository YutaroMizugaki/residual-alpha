import Link from "next/link";

import { SourceKicker } from "@/components/source-kicker";
import { loadMeta } from "@/lib/data";

export default async function HomePage() {
  const meta = await loadMeta();
  const isFixture = meta.source === "fixture";
  return (
    <main className="mx-auto w-full max-w-3xl flex-1 px-4 py-10">
      <SourceKicker meta={meta} />
      <h1 className="mt-2 text-3xl font-semibold">Residual Alpha</h1>
      <p className="mt-4 text-slate-700">
        Residual-income ranking. Python is the only place that computes Beta,
        CAPM, ROE fade, residual income, and scores. Next.js reads generated
        JSON.
      </p>
      <ul className="mt-6 list-disc space-y-1 pl-5 text-slate-700">
        <li>
          The site ranking is recorded <code>--source auto</code> from
          committed <code>tests/data</code> caches (TOPIX Core30). CI rebuilds
          that JSON. It does not fetch Yahoo, J-Quants, or EDINET.
        </li>
        <li>
          Fixture data (tickers 1001–1006) remains the default
          <code>build_public_data.py</code> path for engine tests. Do not
          commit it over the recorded site JSON.
        </li>
        <li>
          Free Data Provider can load TSE prices from the Yahoo Finance chart
          API and annual equity/income/shares from Yahoo timeseries (no API
          key, no yfinance package)
        </li>
        <li>
          J-Quants can load daily AdjC bars and FY summary rows when
          <code>JQUANTS_API_KEY</code> is set for a live fetch. The free plan
          is enough; a paid Light plan is not required. Free-plan bars can lag
          about 12 weeks — each name shows <code>priceAsOf</code>, the last
          close actually used. Market stays Yahoo Nikkei 225.
        </li>
        <li>
          EDINET source can parse yuho XBRL (book, profit, shares) from cached
          zips; live download needs <code>EDINET_API_KEY</code>
        </li>
        <li>
          Auto source picks the complete price series with more aligned
          returns (J-Quants AdjC vs Yahoo; J-Quants wins ties) and the first
          complete fundamentals cache per name (EDINET, then J-Quants, then
          Yahoo). Operator refresh is
          <code>scripts/refresh_public_data.py</code>; there is no scheduled
          GitHub Actions cron
        </li>
        <li>No database or backend API</li>
        {isFixture ? (
          <li>Tickers 1001–1006 are fictional test companies</li>
        ) : (
          <li>
            Recorded prices and filings can lag. Each name shows its
            <code>priceAsOf</code> and fundamentals as-of. Not investment
            advice.
          </li>
        )}
      </ul>
      <p className="mt-8">
        <Link
          href="/ranking"
          className="inline-block rounded-md bg-slate-900 px-4 py-2 text-white"
        >
          Open ranking
        </Link>
      </p>
    </main>
  );
}
