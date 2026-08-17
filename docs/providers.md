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

Yahoo timeseries fields:

- `annualStockholdersEquity` → book value (JPY → million JPY)
- `annualNetIncomeCommonStockholders` → net income
- `annualOrdinarySharesNumber` → shares (count → million shares)

ROE for fiscal year `t` is `NI_t / Equity_{t-1}` (beginning book). Years more
than ~15 months apart are not joined. Missing years are dropped, not filled
with 0 or with a copied latest ROE. The engine still needs 3 history years.

EDINET and J-Quants are **not** called. Both require API keys.

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
```

Optional overlay: `scripts/providers/fundamentals.json`. Empty by default.
Overlay fills only fields that are still missing.

## Units

Unchanged: book value million JPY, shares million shares, price JPY/share,
rates as decimals.

Non-JPY equity/income series are rejected.

## Tests

Provider tests use recorded files under `tests/data/`. They do not hit the
network.
