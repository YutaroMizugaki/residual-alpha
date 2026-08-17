import { RankingTable } from "@/components/ranking-table";
import { loadRankings } from "@/lib/data";

export default async function RankingPage() {
  const rows = await loadRankings();

  return (
    <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-8">
      <p className="text-sm font-semibold tracking-wide text-amber-800 uppercase">
        Fixture Data
      </p>
      <h1 className="mt-1 text-2xl font-semibold">Ranking</h1>
      <p className="mt-2 max-w-3xl text-sm text-slate-600">
        Scores and prices come from Python-generated static JSON. Amounts are
        million JPY / million shares in the engine; prices here are JPY per
        share. Fictional issuers only.
      </p>
      <div className="mt-6">
        <RankingTable rows={rows} />
      </div>
    </main>
  );
}
