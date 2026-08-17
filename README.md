# residual-alpha

Residual-income ranking. Python computes valuation; Next.js displays static JSON.

**Current status:** Fixture MVP + Free Data Provider (prices only).

Displayed data follows `public/data/meta.json`. The committed site is fixture data (fictional tickers). Free prices are opt-in and not used by CI.

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

Provider tests use recorded files. They do not call Yahoo, Stooq, or EDINET.

## Build public data (fixture, default)

```bash
python scripts/build_public_data.py
```

Writes `public/data/rankings.json`, `public/data/meta.json`, and `public/data/stocks/*.json`.

## Free prices (optional, not CI)

```bash
python scripts/fetch_free_data.py
python scripts/build_public_data.py --source free
```

Fundamentals are not fetched. Names without book value/ROE are excluded from ranking. Missing is not replaced with 0.

## Run frontend

```bash
python scripts/build_public_data.py
npm run dev
```

Then open `/ranking`.
