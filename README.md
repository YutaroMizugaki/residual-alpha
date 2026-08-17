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

Recorded test charts under `tests/data/yahoo/` are compact timestamp + close
JSON, inner-joined to Nikkei 225. After a live fetch, compact before copying
into that directory:

```bash
python scripts/compact_yahoo_charts.py --src data/raw/yahoo --dst tests/data/yahoo --align
```

The compact script does not fetch, does not write `public/data`, and is not CI.

## J-Quants (optional, not CI)

Needs `JQUANTS_API_KEY` for live download. Do not commit the key. The
**free plan is enough**; a paid Light plan is not required. Free-plan
daily bars can lag about 12 weeks. That is accepted: each name shows
`priceAsOf` (the last close actually used). Dates are not filled forward.
Live fetch clamps the bars window to the plan's covered dates (HTTP 400
otherwise) and paces requests for the free plan's 5 req/min limit.

```bash
python scripts/fetch_jquants_data.py
python scripts/build_public_data.py --source jquants
```

Prices prefer cached J-Quants daily AdjC, then Yahoo chart. Market stays
Yahoo Nikkei 225. Fundamentals come from J-Quants FY summary rows.

After a live fetch, compact universe caches before copying into
`tests/data/jquants` and `tests/data/jquants_bars`. Empty AdjC and
non-positive AdjC are dropped, not filled with `0`. Files such as
`empty_adjc.json` stay out of the write set.

```bash
python scripts/compact_jquants_caches.py \
  --src-summaries data/raw/jquants --src-bars data/raw/jquants_bars \
  --dst-summaries tests/data/jquants --dst-bars tests/data/jquants_bars
```

`--existing-only` skips universe names that have no cache. It does not
invent the missing names. The compact script does not fetch, does not
write `public/data`, and is not CI.

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

`--source auto` uses cached files only. Prices per name: the complete series
with more aligned returns (J-Quants daily AdjC vs Yahoo chart; J-Quants wins
ties). Fundamentals per name: first complete source among EDINET
XBRL, J-Quants FY summary, then Yahoo timeseries. Sources are not mixed
inside one name. Recorded Yahoo charts cover ~1y of daily closes aligned to
Nikkei 225 for all 10 universe names.
Stock detail JSON includes per-name `priceSource` and `fundamentalsSource`.
Ranking JSON includes the same per-name labels plus `returnCount` (aligned
daily returns used for beta), `roeCount` (ROE history years used for
normalized ROE), `priceAsOf` (last close date), and `fundamentalsAsOf`
(fiscal year-end). Universe `meta.json` is the union across names.

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
