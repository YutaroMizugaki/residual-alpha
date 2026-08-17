import type { DataMeta } from "@/lib/meta-types";

export function DataBanner({ meta }: { meta: DataMeta }) {
  const asOf = meta.asOfDate ? ` As of ${meta.asOfDate}.` : "";
  return (
    <div className="border-b border-amber-300 bg-amber-100 text-amber-950">
      <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-2 px-4 py-2 text-sm">
        <p className="font-semibold tracking-wide uppercase">{meta.sourceLabel}</p>
        <p>
          {meta.disclaimerEn}
          {asOf}
        </p>
      </div>
    </div>
  );
}
