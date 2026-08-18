# residual-alpha

Residual-income ranking. Python computes valuation; Next.js displays static JSON.

**Current status:** Fixture engine tests + a 10-name listed universe on the site. The committed UI JSON is `--source auto --recorded` (Yahoo / J-Quants / EDINET caches under `tests/data`). Live fetch, operator `data/raw`, and GitHub Actions cron are not used by CI.

Displayed data follows `public/data/meta.json`. Tickers are real TSE names from recorded caches, not live API calls. Fixture data (fictional 1001–1006) remains the default `build_public_data.py` path for engine tests. There is no GitHub Actions cron.

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

## Build public data (site: recorded auto)

```bash
python scripts/build_public_data.py --source auto --recorded
```

Writes `public/data/rankings.json`, `public/data/meta.json`, and `public/data/stocks/*.json` from committed caches under `tests/data`. CI rebuilds this way and fails if `public/data` drifts. It does not fetch Yahoo / J-Quants / EDINET and does not read `data/raw`.

## Build public data (fixture, engine tests)

```bash
python scripts/build_public_data.py
```

Fictional issuers 1001–1006. Used by pytest. Do not commit this over the recorded site JSON.

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
Free-plan summaries currently return about two annual FY years (one
beginning-book ROE). That is not padded to three years, so `--source
jquants` stays ranking-ineligible until a complete lower-tier source
(Yahoo / EDINET) is used via `--source auto`.

After a live fetch, compact universe caches before copying into
`tests/data/jquants` and `tests/data/jquants_bars`. Empty AdjC and
non-positive AdjC are dropped, not filled with `0`. Files such as
`empty_adjc.json` stay out of the write set. `--keep-existing` leaves
the recorded 7203 / 6758 / 9984 fixtures (4 FY years and short
Yahoo-aligned bars) in place.

```bash
python scripts/compact_jquants_caches.py \
  --src-summaries data/raw/jquants --src-bars data/raw/jquants_bars \
  --dst-summaries tests/data/jquants --dst-bars tests/data/jquants_bars \
  --keep-existing
```

`--existing-only` skips universe names that have no cache. It does not
invent the missing names. The compact script does not fetch, does not
write `public/data`, and is not CI.

## EDINET XBRL (optional, not CI)

Needs `EDINET_API_KEY` to download zips. Do not commit the key. Discovery uses
cached document lists. Pass each filing date with `--date`; this repo does not
crawl a date range.

```bash
python scripts/fetch_edinet_list.py --date 2026-06-15 --date 2026-06-22
python scripts/fetch_edinet_xbrl.py
python scripts/build_public_data.py --source edinet
```

After a live zip fetch, compact universe caches before copying into
`tests/data/edinet_xbrl`. Compact keeps equity, profit, issued shares, and
treasury shares. Line-item members (capital stock, rows) are dropped, not
treated as total equity. Missing treasury stays missing, not `0`.
`--keep-existing` leaves the recorded 7203 / 6758 / 9984 fixtures in place.

```bash
python scripts/compact_edinet_xbrl.py \
  --src data/raw/edinet_xbrl \
  --dst tests/data/edinet_xbrl \
  --keep-existing
```

`--existing-only` skips universe names that have no cache. It does not
invent the missing names. The compact script does not fetch, does not
write `public/data`, and is not CI.

## Auto source + operator refresh (optional, not CI)

`--source auto` uses cached files only. Prices per name: the complete series
with more aligned returns (J-Quants daily AdjC vs Yahoo chart; J-Quants wins
ties). Fundamentals per name: first complete source among EDINET
XBRL, J-Quants FY summary, then Yahoo timeseries. Sources are not mixed
inside one name. Recorded Yahoo charts cover ~1y of daily closes aligned to
Nikkei 225 for all 10 universe names. Recorded EDINET yuho XBRL also covers
all 10, so `--source auto` uses `edinet_xbrl` for fundamentals. Recorded
J-Quants FY + AdjC cover all 10; free-plan extras have ~2 FY years and
shorter/lagged bars, so auto still uses the longer Yahoo chart for prices
and does not use those incomplete FY rows.
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
Do not commit live `public/data` from `data/raw`. Restore the site with
`python scripts/build_public_data.py --source auto --recorded`.

## Run frontend

```bash
python scripts/build_public_data.py --source auto --recorded
npm run dev
```

Then open `/ranking`.
