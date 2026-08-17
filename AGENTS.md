<!-- BEGIN:nextjs-agent-rules -->

# This is NOT the Next.js you know

This version has breaking changes — APIs, conventions, and file structure may all differ from your training data. Read the relevant guide in `node_modules/next/dist/docs/` (resolved from this file's directory; in monorepos the `next` package may not be visible from the repo root) before writing any code. Heed deprecation notices.

This block is written and re-added by `next dev` — verify at `node_modules/next/dist/server/lib/generate-agent-files.js`. Removing it from a diff only re-creates the uncommitted change; committing it with your work keeps the tree clean.

<!-- END:nextjs-agent-rules -->

## Cursor Cloud specific instructions

`residual-alpha` is a single-repo fixture MVP: a Python quant engine computes valuations and writes static JSON, which a Next.js 16 (App Router, Turbopack, React 19) frontend renders. There is no database or backend API. CI always builds fixture data. Optional Yahoo / J-Quants / EDINET fetch scripts are not run in CI and must not commit API keys.

- Dependencies are refreshed automatically on startup (`pip install -r requirements.txt` for `numpy`/`pytest`, `npm ci` for the frontend). No manual install is needed.
- `pytest` is installed to `~/.local/bin`, which is not on `PATH`. Run tests with `python3 -m pytest` (config in `pytest.ini`; sources under `scripts/` via `pythonpath`).
- Standard commands (see `README.md` / `package.json`): tests `python3 -m pytest`; lint `npm run lint`; build data `python3 scripts/build_public_data.py`; dev server `npm run dev` (serves `http://localhost:3000`, routes `/`, `/ranking`, `/stocks/<ticker>`).
- Optional `--source auto` reads cached prices (J-Quants daily AdjC, then Yahoo chart; market is Yahoo Nikkei 225) and the first complete fundamentals source per name (EDINET XBRL → J-Quants FY → Yahoo timeseries). A partial higher-tier cache does not block a complete lower-tier cache. `scripts/refresh_public_data.py` is an operator command, not CI and not a GitHub Actions cron. Do not commit live `public/data` from auto/free/jquants/edinet; restore with `python3 scripts/build_public_data.py`.
- Before opening or updating a pull request, do one self-review of the branch diff. Look for architecture breaks (Python computes, Next.js displays JSON), missing financials coerced to 0, mixed fundamentals inside one name, live `public/data` from auto/free/jquants/edinet, API keys, and GitHub Actions cron. Fix what you find, then submit the PR.
- The frontend reads `public/data/rankings.json` and `public/data/stocks/*.json`. These are committed, but if you change the Python engine or fixtures (`scripts/`), re-run `python3 scripts/build_public_data.py` to regenerate them before viewing the UI.
- Running `npm run dev` (or `next build`) regenerates `AGENTS.md` and `CLAUDE.md` via Next.js (`next.config.ts` `agentRules`). If they show as modified, commit them with your work to keep the tree clean; do not delete the `nextjs-agent-rules` block.
