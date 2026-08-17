export type ExclusionReason = string;

export type RankingRow = {
  rank: number | null;
  ticker: string;
  companyName: string;
  price: number | null;
  intrinsicPrice: number | null;
  intrinsicUpside: number | null;
  betaAdjusted: number | null;
  costOfEquity: number | null;
  normalizedRoe: number | null;
  excessRoe: number | null;
  valuationScore: number | null;
  qualityScore: number | null;
  riskScore: number | null;
  totalScore: number | null;
  eligible: boolean;
  exclusionReasons: ExclusionReason[];
};

export type ForecastYear = {
  year: number;
  beginningBookValue: number;
  roe: number;
  netIncome: number;
  equityCharge: number;
  residualIncome: number;
  discountFactor: number;
  pvResidualIncome: number;
  dividend: number;
  endingBookValue: number;
};

export type StockDetail = {
  ticker: string;
  companyName: string;
  price: number | null;
  betaRaw: number | null;
  betaAdjusted: number | null;
  betaStatus: string;
  riskFreeRate: number | null;
  equityRiskPremium: number | null;
  costOfEquity: number | null;
  latestRoe: number | null;
  normalizedRoe: number | null;
  normalizedRoeStatus: string;
  excessRoe: number | null;
  bookValue: number | null;
  sharesOutstanding: number | null;
  intrinsicEquityValue: number | null;
  intrinsicPrice: number | null;
  intrinsicUpside: number | null;
  valuationScore: number | null;
  qualityScore: number | null;
  riskScore: number | null;
  totalScore: number | null;
  eligible: boolean;
  exclusionReasons: ExclusionReason[];
  forecast: ForecastYear[];
  priceAsOf?: string | null;
  fundamentalsAsOf?: string | null;
};
