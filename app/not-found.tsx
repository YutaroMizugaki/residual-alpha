import Link from "next/link";

export default function NotFound() {
  return (
    <main className="mx-auto w-full max-w-3xl flex-1 px-4 py-16">
      <p className="text-sm font-semibold tracking-wide text-amber-800 uppercase">
        Fixture Data
      </p>
      <h1 className="mt-2 text-2xl font-semibold">Not found</h1>
      <p className="mt-2 text-slate-600">
        That ticker is not in the fixture set. This is a 404, not a calculation
        error.
      </p>
      <p className="mt-6">
        <Link href="/ranking" className="underline">
          Back to ranking
        </Link>
      </p>
    </main>
  );
}
