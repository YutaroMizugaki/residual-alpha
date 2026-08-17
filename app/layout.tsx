import type { Metadata } from "next";
import Link from "next/link";

import { DataBanner } from "@/components/data-banner";
import { SiteFooter } from "@/components/site-footer";
import { loadMeta } from "@/lib/data";

import "./globals.css";

export const metadata: Metadata = {
  title: "Residual Alpha",
  description: "Residual income ranking from Python-generated static JSON.",
};

export default async function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  const meta = await loadMeta();
  return (
    <html lang="ja">
      <body className="flex min-h-screen flex-col bg-slate-100 text-slate-900 antialiased">
        <DataBanner meta={meta} />
        <header className="border-b border-slate-200 bg-white">
          <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-3">
            <Link href="/" className="font-semibold">
              Residual Alpha
            </Link>
            <nav className="flex gap-4 text-sm">
              <Link href="/ranking" className="hover:underline">
                Ranking
              </Link>
            </nav>
          </div>
        </header>
        {children}
        <SiteFooter meta={meta} />
      </body>
    </html>
  );
}
