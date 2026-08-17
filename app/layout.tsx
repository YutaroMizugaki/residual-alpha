import type { Metadata } from "next";
import Link from "next/link";

import { FixtureBanner } from "@/components/fixture-banner";
import { SiteFooter } from "@/components/site-footer";

import "./globals.css";

export const metadata: Metadata = {
  title: "Residual Alpha — Fixture MVP",
  description: "Fixture-only residual income ranking. Test data, not live market prices.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="ja">
      <body className="flex min-h-screen flex-col bg-slate-100 text-slate-900 antialiased">
        <FixtureBanner />
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
        <SiteFooter />
      </body>
    </html>
  );
}
