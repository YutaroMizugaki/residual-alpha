import { readFile } from "node:fs/promises";
import path from "node:path";

import type { RankingRow, StockDetail } from "@/lib/types";

const DATA_DIR = path.join(process.cwd(), "public", "data");

export async function loadRankings(): Promise<RankingRow[]> {
  const file = path.join(DATA_DIR, "rankings.json");
  try {
    const raw = await readFile(file, "utf-8");
    return JSON.parse(raw) as RankingRow[];
  } catch {
    return [];
  }
}

export async function loadStock(ticker: string): Promise<StockDetail | null> {
  if (!/^[0-9A-Za-z]+$/.test(ticker)) {
    return null;
  }
  const file = path.join(DATA_DIR, "stocks", `${ticker}.json`);
  try {
    const raw = await readFile(file, "utf-8");
    return JSON.parse(raw) as StockDetail;
  } catch {
    return null;
  }
}
