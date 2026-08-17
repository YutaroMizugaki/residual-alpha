export function FixtureBanner() {
  return (
    <div className="border-b border-amber-300 bg-amber-100 text-amber-950">
      <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-2 px-4 py-2 text-sm">
        <p className="font-semibold tracking-wide uppercase">Fixture Data</p>
        <p>Test data only. Tickers and figures are fictional, not live market prices.</p>
      </div>
    </div>
  );
}
