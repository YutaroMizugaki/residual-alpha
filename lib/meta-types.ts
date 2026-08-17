export type DataMeta = {
  source: string;
  sourceLabel: string;
  priceSource: string;
  fundamentalsSource: string;
  marketSymbol: string | null;
  asOfDate: string | null;
  priceLagNote?: string | null;
  priceLagNoteJa?: string | null;
  disclaimerJa: string;
  disclaimerEn: string;
};

export const JQUANTS_FREE_LAG_NOTE =
  "J-Quants free-plan daily bars can lag about 12 weeks. Each name's priceAsOf is the last close used; dates are not filled forward.";

export const DEFAULT_META: DataMeta = {
  source: "fixture",
  sourceLabel: "Fixture Data",
  priceSource: "fixture",
  fundamentalsSource: "fixture",
  marketSymbol: null,
  asOfDate: null,
  priceLagNote: null,
  priceLagNoteJa: null,
  disclaimerJa: "現在表示している銘柄および数値はテスト用fixtureです。",
  disclaimerEn: "Test data only. Tickers and figures are fictional, not live market prices.",
};
