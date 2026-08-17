# residual-alpha

Fixture MVP of a residual-income ranking. Python computes valuation; Next.js displays static JSON.

**Current status: Fixture MVP.** Tickers and numbers are fictional test data, not live market prices.

## Architecture

```text
Fixture → Python quant engine → public/data JSON → Next.js
```

No database, no backend API, no live market feed.

Units: book value in million JPY, shares in million shares, prices in JPY/share, rates as decimals (`0.15` = 15%). Details: `docs/architecture.md`, `docs/methodology.md`.

## Setup

```bash
python -m pip install -r requirements.txt
npm install
```

## Test

```bash
pytest
```

## Build public data

```bash
python scripts/build_public_data.py
```

Writes `public/data/rankings.json` and `public/data/stocks/*.json`.

## Run frontend

```bash
python scripts/build_public_data.py
npm run dev
```

Then open `/ranking` and `/stocks/1001`.
