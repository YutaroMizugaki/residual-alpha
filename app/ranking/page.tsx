import { RankingTable } from "@/components/ranking-table";
import { SourceKicker } from "@/components/source-kicker";
import { loadMeta, loadRankings } from "@/lib/data";

export default async function RankingPage() {
  const [rows, meta] = await Promise.all([loadRankings(), loadMeta()]);
  const isFixture = meta.source === "fixture";

  return (
    <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-8">
      <SourceKicker meta={meta} />
      <h1 className="mt-1 text-2xl font-semibold">Ranking</h1>
      <p className="mt-2 max-w-3xl text-sm text-slate-600">
        Scores and prices come from Python-generated static JSON. Amounts are
        million JPY / million shares in the engine; prices here are JPY per
        share.
        {isFixture
          ? " Fictional issuers only."
          : ` Universe mix: ${meta.priceSource} / ${meta.fundamentalsSource}. Each row shows that name's sources.`}
      </p>
      <div className="mt-6">
        <RankingTable rows={rows} />
      </div>
    </main>
  );
}
