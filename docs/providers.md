# Data providers

Python remains the only place that computes valuation. Providers only assemble
the same snapshot schema the fixture already uses.

```text
Provider snapshot
  → Python quant engine
  → public/data JSON
  → Next.js
```

## Sources

| Source | Prices | Fundamentals | API key | Default |
| --- | --- | --- | --- | --- |
| `fixture` | fictional JSON | fictional JSON | no | yes (CI) |
| `free` | Yahoo Finance chart JSON | Yahoo annual timeseries | no | no |
| `jquants` | J-Quants daily AdjC, else Yahoo chart | J-Quants v2 `/fins/summary` FY rows | `JQUANTS_API_KEY` for live fetch (free plan is enough) | no |
| `edinet` | Yahoo Finance chart JSON | EDINET yuho XBRL instance | `EDINET_API_KEY` to download zips | no |
| `auto` | complete series with more aligned returns: J-Quants daily AdjC vs Yahoo chart (J-Quants wins ties) | first complete source per name: EDINET XBRL → J-Quants FY → Yahoo timeseries | keys only for live fetch of keyed caches | no |

Yahoo timeseries fields (free source):

- `annualStockholdersEquity` → book value (JPY → million JPY)
- `annualNetIncomeCommonStockholders` → net income
- `annualOrdinarySharesNumber` → shares (count → million shares)

J-Quants daily bars (jquants / auto prices):

- `AdjC` → split-adjusted close (JPY per share)
- Empty / null `AdjC` is missing, not 0. Unadjusted `C` is not used.
- No-trade days stay missing. Market for beta remains Yahoo Nikkei 225;
  J-Quants does not publish Nikkei OHLC.
- Live fetch needs `JQUANTS_API_KEY`. The **free plan is enough**; a paid
  Light plan is not required. Free-plan bars omit the last ~12 weeks.
  That lag is accepted. Each name's `priceAsOf` is the last close used.
  When any name uses `jquants_bars`, `meta.json` sets `priceLagNote`.
  Dates are not filled forward to today. A `to` date past the plan window
  is HTTP 400; the fetch clamps `from`/`to` to the covered range. Free
  plan is 5 req/min; live calls wait between requests and retry HTTP 429.

J-Quants FY fields (jquants source):

- `ShEq` (else `Eq`) → book value (JPY → million JPY)
- `NP` → net income
- `ShOutFY − TrShFY` → shares (both must be present; empty treasury is not 0)
- Free-plan `/fins/summary` currently returns about two annual FY rows
  per name (one beginning-book ROE). That is not padded to three years.
  Recorded 7203 / 6758 / 9984 keep four FY years for parser tests.

EDINET XBRL (edinet source), from the PublicDoc instance in a type=1 zip:

- `EquityAttributableToOwnersOfParent(IFRS)` else `ShareholdersEquity` / `NetAssets`
- `ProfitLossAttributableToOwnersOfParent(IFRS)`
- issued shares (DEI, else fiscal-year-end issued, else 5-year summary) minus
  treasury shares (DEI, else treasury-shares-etc total). Both must be present.
- Line-item members (`CapitalStockMember`, `Row1Member`, …) are skipped.
  Consolidation members are not skipped. Consolidated contexts win over
  non-consolidated. Quarterly durations are skipped.
- `xsi:nil` is missing, not 0. Non-JPY monetary units are rejected.

Only `CurPerType=FY` rows are used for J-Quants. Consolidated filings win over non-consolidated
for the same fiscal year-end. Reported `ROE` from the API is ignored; the engine
computes beginning-book ROE.

ROE for fiscal year `t` is `NI_t / Equity_{t-1}` (beginning book). Years more
than ~15 months apart are not joined. Missing years are dropped, not filled
with 0 or with a copied latest ROE. The engine still needs 3 history years.

EDINET v2 document lists can be fetched with `EDINET_API_KEY`. 401/403 is a
fetch failure, not an empty filing list. Yuho XBRL zips (`type=1`) are parsed
from cache; this repo does not crawl every calendar day to discover filings.

Stooq live HTTP is **not** used. Automated requests receive an HTML bot-wall.
Stooq daily CSV files can still be parsed if an operator supplies them.

## Commands

```bash
# default: fixture, deterministic, used by CI
python scripts/build_public_data.py

# download Yahoo chart + fundamentals JSON (network; not run in CI)
python scripts/fetch_free_data.py

# compact live Yahoo charts to timestamp + close, inner-join to Nikkei
# (not CI; does not write public/data; missing days dropped, not filled with 0)
python scripts/compact_yahoo_charts.py --src data/raw/yahoo --dst tests/data/yahoo --align

# rebuild UI JSON from cached Yahoo files
python scripts/build_public_data.py --source free

# J-Quants FY summaries (network; needs JQUANTS_API_KEY; not run in CI)
# also downloads /equities/bars/daily into data/raw/jquants_bars
python scripts/fetch_jquants_data.py
python scripts/build_public_data.py --source jquants

# compact live J-Quants FY + AdjC to recorded-test form
# (not CI; does not write public/data; empty/non-positive AdjC dropped, not filled with 0)
python scripts/compact_jquants_caches.py \
  --src-summaries data/raw/jquants --src-bars data/raw/jquants_bars \
  --dst-summaries tests/data/jquants --dst-bars tests/data/jquants_bars \
  --keep-existing
# --existing-only skips names with no cache; it does not invent missing names
# --keep-existing leaves recorded 7203/6758/9984 fixtures in place

# EDINET list then yuho XBRL zips (network; needs EDINET_API_KEY; not run in CI)
python scripts/fetch_edinet_list.py --date 2026-06-22
python scripts/fetch_edinet_xbrl.py
python scripts/build_public_data.py --source edinet

# compact live yuho zips to instance facts (equity, profit, issued, treasury)
# (not CI; does not write public/data; line-item members dropped; missing not 0)
python scripts/compact_edinet_xbrl.py \
  --src data/raw/edinet_xbrl --dst tests/data/edinet_xbrl \
  --keep-existing
# --existing-only skips names with no cache; it does not invent missing names
# --keep-existing leaves recorded 7203/6758/9984 fixtures in place

# operator refresh (not CI, not a GitHub Actions cron)
python scripts/refresh_public_data.py --dry-run
python scripts/refresh_public_data.py --source auto
```

`--source auto` is cache-only. Per name it takes the **complete** price
series with more aligned returns (J-Quants daily AdjC vs Yahoo chart;
J-Quants wins ties) and the first **complete** fundamentals source (book,
shares, and 3 beginning-book ROE years). It does not mix sources inside one
issuer. A partial or short higher-tier cache does not block a longer complete
lower-tier cache. If nothing is complete, the first partial is kept. Names
without a cached chart or financials stay ranking-ineligible; missing is not 0.

Each stock row carries its own `priceSource` and `fundamentalsSource` in
both ranking JSON and stock detail JSON. Ranking JSON also carries
`returnCount`, `roeCount` (ROE history years used for normalized ROE),
`priceAsOf` (last close date), and `fundamentalsAsOf` (fiscal year-end).
Missing dates and counts stay missing (`null`), not `0`. Do not pad short
ROE history.
Universe `meta.json` stays the union across names (`jquants_bars+yahoo_chart`
when auto mixes). The stock page reads the per-name labels, not the mix.
Missing sources stay missing (`null`), not `0` and not another name's source.

`refresh_public_data.py --source free` fetches only Yahoo even if keyed env
vars are set. `--source jquants` / `--source edinet` fetch Yahoo plus that
keyed cache when the matching key is present.

Fetch failures print a warning and continue; a failed build still fails the
script. It does not crawl EDINET filing dates. Run
`fetch_edinet_list.py --date YYYY-MM-DD` first if you need new yuho zips.

The listed-name universe in `scripts/providers/universe.json` has 10 tickers.
Recorded Yahoo chart and annual timeseries cover all 10. Charts are ~1y of
daily closes, inner-joined to Nikkei 225 (missing days dropped, not filled
with 0). `scripts/compact_yahoo_charts.py --align` writes that compact form
from a live Yahoo chart dump; it does not fetch and does not write
`public/data`. Recorded J-Quants FY + AdjC cover all 10 names.
7203 / 6758 / 9984 keep four FY years and short Yahoo-aligned bars for
parser tests. The other seven are free-plan dumps: about two FY years
(one beginning-book ROE, not padded) and daily AdjC through the plan
window (`priceAsOf` 2026-05-25). Recorded EDINET yuho XBRL covers all 10
names. 7203 / 6758 / 9984 keep synthetic four-year fixtures. The other
seven are compacted PublicDoc facts from 2023–2026 yuho zips (3 beginning-book
ROE years; missing treasury is not 0). `scripts/compact_edinet_xbrl.py`
writes instance XML from a live zip dump; `--existing-only` skips names with
no cache instead of failing; `--keep-existing` does not overwrite destination
files that already exist. It does not fetch, does not invent missing names,
and does not write `public/data`. `scripts/compact_jquants_caches.py` writes FY rows and
AdjC-only bars from a live dump; `--existing-only` skips names with no cache
instead of failing; `--keep-existing` does not overwrite destination files
that already exist. It does not fetch, does not invent missing names, and
does not write `public/data`. `--source auto` prefers the longer complete
Yahoo series when free-plan bars are shorter or FY history is incomplete;
`--source jquants` still uses those bars first. Names without a keyed cache
fall through to Yahoo in `--source auto`, or stay ranking-ineligible on
`--source jquants` / `--source edinet`. Missing is not 0.

Do not commit API keys. `.env*` is gitignored. Do not commit live
`public/data` from `--source auto` / `free` / `jquants` / `edinet`; CI rebuilds
fixture JSON.

Optional overlay: `scripts/providers/fundamentals.json`. Empty by default.
Overlay fills only fields that are still missing.

## Units

Unchanged: book value million JPY, shares million shares, price JPY/share,
rates as decimals.

Non-JPY equity/income series are rejected.

## Tests

Provider tests use recorded files under `tests/data/`. They do not hit the
network.
