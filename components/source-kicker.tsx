import type { DataMeta } from "@/lib/meta-types";

export function SourceKicker({ meta }: { meta: DataMeta }) {
  return (
    <p className="text-sm font-semibold tracking-wide text-amber-800 uppercase">
      {meta.sourceLabel}
    </p>
  );
}
