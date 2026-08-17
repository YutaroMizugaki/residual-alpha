import type { DataMeta } from "@/lib/meta-types";

export function SiteFooter({ meta }: { meta: DataMeta }) {
  return (
    <footer className="mt-auto border-t border-slate-200 bg-slate-50">
      <div className="mx-auto max-w-6xl px-4 py-6 text-sm text-slate-600">
        <p>{meta.disclaimerJa}</p>
        <p className="mt-1">
          Residual Alpha — Python computes valuation; this UI only displays
          static JSON. Universe: {meta.priceSource} / {meta.fundamentalsSource}
          {meta.asOfDate ? ` (${meta.asOfDate})` : ""}.
        </p>
      </div>
    </footer>
  );
}
