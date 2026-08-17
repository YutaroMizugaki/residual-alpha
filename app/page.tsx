import Link from "next/link";

export default function HomePage() {
  return (
    <main className="mx-auto w-full max-w-3xl flex-1 px-4 py-10">
      <p className="text-sm font-semibold tracking-wide text-amber-800 uppercase">
        Fixture Data
      </p>
      <h1 className="mt-2 text-3xl font-semibold">Residual Alpha</h1>
      <p className="mt-4 text-slate-700">
        Fixture MVP of a residual-income ranking. Python is the only place that
        computes Beta, CAPM, ROE fade, residual income, and scores. Next.js
        reads the generated JSON and displays it.
      </p>
      <ul className="mt-6 list-disc space-y-1 pl-5 text-slate-700">
        <li>No live market data, EDINET, or J-Quants</li>
        <li>No database or backend API</li>
        <li>Tickers 1001–1006 are fictional test companies</li>
      </ul>
      <p className="mt-8">
        <Link
          href="/ranking"
          className="inline-block rounded-md bg-slate-900 px-4 py-2 text-white"
        >
          Open fixture ranking
        </Link>
      </p>
    </main>
  );
}
