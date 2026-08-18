# Architecture

Residual Alpha builds a static ranking from a provider snapshot.

## Source of truth

```text
Python = computation
Static JSON = interface
Next.js = presentation
```

```text
Provider snapshot
  → Python quant engine
  → public/data/*.json
  → Next.js UI
```

TypeScript does not recompute Beta, CAPM, residual income, intrinsic price, or scores.

Default **site** provider is **auto** from recorded `tests/data` caches
(`build_public_data.py --source auto --recorded`). Default **CLI** without
flags is still **fixture** (fictional issuers, engine tests). Optional **free**,
**jquants**, **edinet**, and live **auto** from `data/raw` remain operator
paths. **jquants** prices prefer
J-Quants daily AdjC, then Yahoo chart. The J-Quants **free plan is enough**;
free-plan bars can lag about 12 weeks and that lag is labeled via
`priceAsOf` / `priceLagNote`. **auto** prices pick the complete
series with more aligned returns (J-Quants wins ties). Market stays Yahoo
Nikkei 225. **auto** picks the first complete fundamentals source per name
(EDINET XBRL, then J-Quants FY, then Yahoo timeseries). See
`docs/providers.md`.

## What this phase does not include

```text
No DB
No backend API
No cloud worker
No EDINET date-range crawl
No live Stooq HTTP (bot-wall)
No GitHub Actions cron
No authentication
No backtest
No trading
```

## Layout

- `scripts/models/` — valuation math
- `scripts/providers/` — fixture, Yahoo, J-Quants summary + daily bars, EDINET list + XBRL
- `scripts/fixtures/stocks.json` — fictional inputs
- `scripts/build_public_data.py` — writes `public/data/` (site: `--source auto --recorded`)
- `scripts/refresh_public_data.py` — optional operator fetch + rebuild (no cron)
- `scripts/fetch_free_data.py` — optional Yahoo chart + timeseries download
- `scripts/compact_yahoo_charts.py` — optional compact/align of Yahoo chart JSON for recorded tests (no fetch, no cron)
- `scripts/fetch_jquants_data.py` — optional J-Quants FY summary + daily bars download
- `scripts/compact_jquants_caches.py` — optional compact of J-Quants FY + AdjC JSON for recorded tests (no fetch, no cron)
- `scripts/fetch_edinet_list.py` — optional EDINET document list (repeat `--date`; no range crawl)
- `scripts/fetch_edinet_xbrl.py` — optional EDINET yuho XBRL zip download
- `scripts/compact_edinet_xbrl.py` — optional compact of EDINET yuho XBRL for recorded tests (no fetch, no cron)
- `scripts/providers/universe.json` — 10 listed names for non-fixture sources
- `tests/` — pytest (no live network)
- `app/`, `components/`, `lib/` — Next.js display only. Ranking JSON includes per-name sources, `returnCount`, `roeCount`, `priceAsOf`, and `fundamentalsAsOf`.
- `vercel.json` — Vercel build settings (`npm ci`, `npm run build`; reads committed `public/data`, no Python on platform)
- `.github/workflows/deploy.yml` — optional Vercel production deploy after `test` on `main` (needs repo secrets; not a cron)

## Units

- Book value and equity value: million JPY
- Shares outstanding: million shares
- Price and intrinsic price: JPY per share
- Rates and returns: decimals (`0.15` = 15%)
