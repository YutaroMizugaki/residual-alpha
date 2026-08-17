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
| `free` | Yahoo Finance chart JSON | overlay file only | no | no |

EDINET and J-Quants are **not** called in this phase. Both require API keys.

Stooq live HTTP is **not** used. Automated requests receive an HTML bot-wall.
Stooq daily CSV files can still be parsed if an operator supplies them.

## Commands

```bash
# default: fixture, deterministic, used by CI
python scripts/build_public_data.py

# download Yahoo chart JSON (network; not run in CI)
python scripts/fetch_free_data.py

# rebuild UI JSON from cached Yahoo files
python scripts/build_public_data.py --source free
```

Without a fundamentals overlay, free-source names have prices and beta inputs
but are ranking-ineligible (`missing_book_value` / `missing_roe`). Missing
stays missing. It is not replaced with 0.

Optional overlay: `scripts/providers/fundamentals.json`. Empty by default.
That file is a manual snapshot, not live EDINET.

## Units

Unchanged: book value million JPY, shares million shares, price JPY/share,
rates as decimals.

Yahoo chart closes are JPY per share. Non-JPY series are rejected.

## Tests

Provider tests use recorded files under `tests/data/`. They do not hit the
network.
