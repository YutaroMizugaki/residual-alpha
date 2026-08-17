export function SiteFooter() {
  return (
    <footer className="mt-auto border-t border-slate-200 bg-slate-50">
      <div className="mx-auto max-w-6xl px-4 py-6 text-sm text-slate-600">
        <p>現在表示している銘柄および数値はテスト用fixtureです。</p>
        <p className="mt-1">
          Residual Alpha Fixture MVP — Python computes valuation; this UI only
          displays static JSON. No live market data.
        </p>
      </div>
    </footer>
  );
}
