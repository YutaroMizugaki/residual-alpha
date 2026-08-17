# residual-alpha

Residual-income ranking. Python computes valuation; Next.js displays static JSON.

**Current status:** Fixture MVP + Free Data Provider (Yahoo) + keyed J-Quants FY summaries and daily AdjC bars + EDINET yuho XBRL + `--source auto` fallback and a 10-name listed universe.

Displayed data follows `public/data/meta.json`. The committed site is fixture data (fictional tickers). Free, J-Quants, EDINET, and auto sources are opt-in and not used by CI. There is no GitHub Actions cron.

## Architecture

```text
Provider snapshot → Python quant engine → public/data JSON → Next.js
```

No database, no backend API. Details: `docs/architecture.md`, `docs/methodology.md`, `docs/providers.md`.

Units: book value in million JPY, shares in million shares, prices in JPY/share, rates as decimals (`0.15` = 15%).

## Setup

```bash
python -m pip install -r requirements.txt
npm install
```

## Test

```bash
pytest
```

Provider tests use recorded files. They do not call Yahoo, Stooq, EDINET, or J-Quants.

## Build public data (fixture, default)

```bash
python scripts/build_public_data.py
```

Writes `public/data/rankings.json`, `public/data/meta.json`, and `public/data/stocks/*.json`.

## Free data (optional, not CI)

```bash
python scripts/fetch_free_data.py
python scripts/build_public_data.py --source free
```

Prices from Yahoo chart; fundamentals from Yahoo annual timeseries.
Missing values are not replaced with 0. Not investment advice.

## J-Quants (optional, not CI)

Needs `JQUANTS_API_KEY` for live download. Do not commit the key.

```bash
python scripts/fetch_jquants_data.py
python scripts/build_public_data.py --source jquants
```

Prices prefer cached J-Quants daily AdjC, then Yahoo chart. Market stays
Yahoo Nikkei 225. Fundamentals come from J-Quants FY summary rows.

```bash
# document list (needs EDINET_API_KEY)
python scripts/fetch_edinet_list.py --date 2026-05-08
```

## EDINET XBRL (optional, not CI)

Needs `EDINET_API_KEY` to download zips. Do not commit the key. Discovery uses
cached document lists; this repo does not crawl every filing date.

```bash
python scripts/fetch_edinet_xbrl.py
python scripts/build_public_data.py --source edinet
```

## Auto source + operator refresh (optional, not CI)

`--source auto` uses cached files only. Prices per name: J-Quants daily AdjC,
then Yahoo chart. Fundamentals per name: first complete source among EDINET
XBRL, J-Quants FY summary, then Yahoo timeseries. Sources are not mixed
inside one name. Recorded Yahoo charts cover ~1y of daily closes aligned to
Nikkei 225 for all 10 universe names.
Stock detail JSON includes per-name `priceSource` and `fundamentalsSource`.
Ranking JSON includes the same per-name labels plus `returnCount` (aligned
daily returns used for beta). Universe `meta.json` is the union across names.

```bash
python scripts/refresh_public_data.py --dry-run
python scripts/refresh_public_data.py --source auto
python scripts/build_public_data.py --source auto
```

`refresh_public_data.py` is an operator command. It is not scheduled CI.
Do not commit the resulting live `public/data` JSON.

## Run frontend

```bash
python scripts/build_public_data.py
npm run dev
```

Then open `/ranking`.
