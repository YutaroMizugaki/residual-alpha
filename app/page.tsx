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
        <li>Default build is fixture data (deterministic, used by CI)</li>
        <li>
          Free Data Provider can load TSE prices from the Yahoo Finance chart
          API (no API key, no yfinance package)
        </li>
        <li>EDINET / J-Quants are not fetched (API keys required)</li>
        <li>No database or backend API</li>
        {isFixture ? <li>Tickers 1001–1006 are fictional test companies</li> : null}
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
