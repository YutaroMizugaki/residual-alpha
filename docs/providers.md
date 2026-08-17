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
| `jquants` | Yahoo Finance chart JSON | J-Quants v2 `/fins/summary` FY rows | `JQUANTS_API_KEY` for live fetch | no |
| `edinet` | Yahoo Finance chart JSON | EDINET yuho XBRL instance | `EDINET_API_KEY` to download zips | no |

Yahoo timeseries fields (free source):

- `annualStockholdersEquity` → book value (JPY → million JPY)
- `annualNetIncomeCommonStockholders` → net income
- `annualOrdinarySharesNumber` → shares (count → million shares)

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
python scripts/fetch_jquants_data.py
python scripts/build_public_data.py --source jquants

# EDINET list then yuho XBRL zips (network; needs EDINET_API_KEY; not run in CI)
python scripts/fetch_edinet_list.py --date 2026-05-08
python scripts/fetch_edinet_xbrl.py
python scripts/build_public_data.py --source edinet
```

Do not commit API keys. `.env*` is gitignored.

Optional overlay: `scripts/providers/fundamentals.json`. Empty by default.
Overlay fills only fields that are still missing.

## Units

Unchanged: book value million JPY, shares million shares, price JPY/share,
rates as decimals.

Non-JPY equity/income series are rejected.

## Tests

Provider tests use recorded files under `tests/data/`. They do not hit the
network.
