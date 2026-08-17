# Architecture

Residual Alpha Fixture MVP is a static ranking of fictional issuers.

## Source of truth

```text
Python = computation
Static JSON = interface
Next.js = presentation
```

```text
Fixture JSON
  → Python quant engine
  → public/data/*.json
  → Next.js UI
```

TypeScript does not recompute Beta, CAPM, residual income, intrinsic price, or scores. It loads JSON and formats it.

## What this phase does not include

```text
No DB
No backend API
No cloud worker
No live market data
No EDINET / J-Quants / Yahoo / Stooq
No authentication
No backtest
No trading
```

## Layout

- `scripts/models/` — valuation math
- `scripts/fixtures/stocks.json` — fictional inputs
- `scripts/build_public_data.py` — writes `public/data/`
- `tests/` — pytest
- `app/`, `components/`, `lib/` — Next.js display only

## Units

- Book value and equity value: million JPY
- Shares outstanding: million shares
- Price and intrinsic price: JPY per share
- Rates and returns: decimals (`0.15` = 15%)
