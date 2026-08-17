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
| `jquants` | J-Quants daily AdjC, else Yahoo chart | J-Quants v2 `/fins/summary` FY rows | `JQUANTS_API_KEY` for live fetch | no |
| `edinet` | Yahoo Finance chart JSON | EDINET yuho XBRL instance | `EDINET_API_KEY` to download zips | no |
| `auto` | first complete series per name: J-Quants daily AdjC → Yahoo chart | first complete source per name: EDINET XBRL → J-Quants FY → Yahoo timeseries | keys only for live fetch of keyed caches | no |

Yahoo timeseries fields (free source):

- `annualStockholdersEquity` → book value (JPY → million JPY)
- `annualNetIncomeCommonStockholders` → net income
- `annualOrdinarySharesNumber` → shares (count → million shares)

J-Quants daily bars (jquants / auto prices):

- `AdjC` → split-adjusted close (JPY per share)
- Empty / null `AdjC` is missing, not 0. Unadjusted `C` is not used.
- No-trade days stay missing. Market for beta remains Yahoo Nikkei 225;
  J-Quants does not publish Nikkei OHLC.

J-Quants FY fields (jquants source):

- `ShEq` (else `Eq`) → book value (JPY → million JPY)
- `NP` → net income
- `ShOutFY − TrShFY` → shares (both must be present; empty treasury is not 0)

EDINET XBRL (edinet source), from the PublicDoc instance in a type=1 zip:

- `EquityAttributableToOwnersOfParent(IFRS)` else `ShareholdersEquity` / `NetAssets`
- `ProfitLossAttributableToOwnersOfParent(IFRS)`
- issued shares DEI minus treasury shares DEI (both must be present)
- Consolidated contexts win over non-consolidated. Quarterly durations are skipped.
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

# rebuild UI JSON from cached Yahoo files
python scripts/build_public_data.py --source free

# J-Quants FY summaries (network; needs JQUANTS_API_KEY; not run in CI)
# also downloads /equities/bars/daily into data/raw/jquants_bars
python scripts/fetch_jquants_data.py
python scripts/build_public_data.py --source jquants

# EDINET list then yuho XBRL zips (network; needs EDINET_API_KEY; not run in CI)
python scripts/fetch_edinet_list.py --date 2026-05-08
python scripts/fetch_edinet_xbrl.py
python scripts/build_public_data.py --source edinet

# operator refresh (not CI, not a GitHub Actions cron)
python scripts/refresh_public_data.py --dry-run
python scripts/refresh_public_data.py --source auto
```

`--source auto` is cache-only. Per name it takes the first **complete**
price series (J-Quants daily AdjC, then Yahoo chart) and the first
**complete** fundamentals source (book, shares, and 3 beginning-book ROE
years). It does not mix sources inside one issuer. A partial higher-tier
cache does not block a complete lower-tier cache. If nothing is complete,
the first partial is kept. Names without a cached chart or financials stay
ranking-ineligible; missing is not 0.

`refresh_public_data.py --source free` fetches only Yahoo even if keyed env
vars are set. `--source jquants` / `--source edinet` fetch Yahoo plus that
keyed cache when the matching key is present.

Fetch failures print a warning and continue; a failed build still fails the
script. It does not crawl EDINET filing dates. Run
`fetch_edinet_list.py --date YYYY-MM-DD` first if you need new yuho zips.

The listed-name universe in `scripts/providers/universe.json` has 10 tickers.
Recorded Yahoo chart and annual timeseries cover all 10. J-Quants summaries,
daily bars, and EDINET XBRL still cover Toyota, Sony, and SoftBank. Names
without a keyed cache fall through to Yahoo in `--source auto`, or stay
ranking-ineligible on `--source jquants` / `--source edinet`. Missing is not 0.

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
