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

Default provider is **fixture** (fictional issuers). Optional **free** provider
loads TSE prices from the Yahoo Finance chart API and annual fundamentals from
the Yahoo timeseries API. Optional **jquants** provider keeps Yahoo prices and
loads FY fundamentals from J-Quants `/fins/summary` (live fetch needs
`JQUANTS_API_KEY`). See `docs/providers.md`.

## What this phase does not include

```text
No DB
No backend API
No cloud worker
No EDINET XBRL parsing (list/auth only)
No live Stooq HTTP (bot-wall)
No GitHub Actions cron
No authentication
No backtest
No trading
```

## Layout

- `scripts/models/` — valuation math
- `scripts/providers/` — fixture, Yahoo, J-Quants summary, EDINET list
- `scripts/fixtures/stocks.json` — fictional inputs
- `scripts/build_public_data.py` — writes `public/data/`
- `scripts/fetch_free_data.py` — optional Yahoo chart + timeseries download
- `scripts/fetch_jquants_data.py` — optional J-Quants FY summary download
- `scripts/fetch_edinet_list.py` — optional EDINET document list (no XBRL)
- `tests/` — pytest (no live network)
- `app/`, `components/`, `lib/` — Next.js display only

## Units

- Book value and equity value: million JPY
- Shares outstanding: million shares
- Price and intrinsic price: JPY per share
- Rates and returns: decimals (`0.15` = 15%)
