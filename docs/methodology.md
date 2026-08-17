# Methodology

Rates are decimals (`6.5% = 0.065`). Missing financials are never replaced with `0`.

Missing-metric scoring: weights of available metrics in the same category are redistributed proportionally. A missing P/B discount does not become 0 points inside Valuation. If an entire category cannot be scored, the stock is not score-eligible.

## Raw Beta

```text
beta_raw = cov(stock, market) / var(market)
```

Sample covariance and variance both use `ddof=1`. If market variance is (numerically) zero, the result is invalid — not `0`.

## Adjusted Beta

```text
beta_adjusted = 0.67 × beta_raw + 0.33 × 1.0
```

Then clip to `[0.3, 2.0]`.

## CAPM

```text
ke = rf + beta × ERP
```

Fixture assumptions: `rf = 0.015`, `ERP = 0.05`. If `beta = 1.0`, `ke = 0.065`.

## Normalized ROE

`roe_history` is oldest → newest. The last three observations are the trailing three years.

If at least three history points exist:

```text
roe_3y_median = median(last 3 years)
normalized_roe = 0.6 × latest_roe + 0.4 × roe_3y_median
```

Clip to `[-0.20, 0.40]`. Shorter history is `insufficient_history`, not filled with zeros.

## ROE Fade

10-year path:

```text
Year 1 = normalized_roe
Year 2 = normalized_roe
Year 3 = normalized_roe
Year 10 = cost_of_equity
```

Years 4–10 fade linearly from Year 3 to Year 10.

## Residual Income

Each year, in order:

```text
Beginning Book Value
→ ROE
→ Net Income = ROE × Beginning Book Value
→ Equity Charge = Cost of Equity × Beginning Book Value
→ Residual Income = Net Income − Equity Charge
                 = (ROE − Cost of Equity) × Beginning Book Value
→ Dividend = Net Income × (1 − Retention Ratio)
→ Ending Book Value = Beginning Book Value + Net Income − Dividend
                    = Beginning Book Value + Net Income × Retention Ratio
```

Default `retention_ratio = 0.50`. Retention is the share of earnings kept, not the payout ratio.

## Discount Factor

Year `t` residual income is discounted by `(1 + ke)^t`. Year 1 uses `t = 1`, not `t = 0`.

## Intrinsic Equity Value

```text
Intrinsic Equity Value = Current Book Value + Σ PV(Residual Income)
```

Terminal value is `0`. Current book value is added once.

## Intrinsic Price

```text
Intrinsic Price = Intrinsic Equity Value / Shares Outstanding
Intrinsic Upside = Intrinsic Price / Current Price − 1
```

With book value in million JPY and shares in million shares, intrinsic price is JPY per share.

## Scoring (100 points)

```text
Valuation 50
  Intrinsic Upside 30   (higher better)
  Earnings Yield   10   (higher better; latest ROE × BV / market cap)
  P/B Discount     10   (higher better; 1 − Price/Book)

Quality 30
  Excess ROE       20   (higher better; normalized ROE − ke)
  ROE Stability    10   (lower ROE volatility better)

Risk 20
  Beta             10   (beta near 1.0 is the reference; high beta is penalized)
  Volatility       10   (lower price-return volatility better)
```

Percentile ranks use only stocks that have the metric. Lower-is-better series use `100 − percentile`. Beta is not a higher-is-better percentile.

Eligible stocks are ranked by total score. Incomplete fixture names are kept in JSON with `eligible: false` and `exclusionReasons`.
