export type DataMeta = {
  source: string;
  sourceLabel: string;
  priceSource: string;
  fundamentalsSource: string;
  marketSymbol: string | null;
  asOfDate: string | null;
  disclaimerJa: string;
  disclaimerEn: string;
};

export const DEFAULT_META: DataMeta = {
  source: "fixture",
  sourceLabel: "Fixture Data",
  priceSource: "fixture",
  fundamentalsSource: "fixture",
  marketSymbol: null,
  asOfDate: null,
  disclaimerJa: "現在表示している銘柄および数値はテスト用fixtureです。",
  disclaimerEn: "Test data only. Tickers and figures are fictional, not live market prices.",
};
