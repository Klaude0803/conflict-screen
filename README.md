# conflict-screen

Screen a list of creators against a target brand for **category conflicts**,
**audience geo leverage**, and short **negotiation notes** — then export a
color-coded XLSX.

Runs in **mock mode by default**, so it works with no API key. Wire up the
real [Scrape Creators](https://scrapecreators.com) API when you're ready.

## What it does

For each creator handle you give it, the tool:

1. **Fetches** name, platform, subscribers, audience geo %, and recent
   sponsors (`src/scrape_client.py`). Mock data is clearly labeled `(SAMPLE)`.
   Missing fields are left empty — the tool never invents data — and every
   record carries a `verified` flag.
2. **Screens for conflicts** (`src/conflict.py`) over a 12-month lookback:
   - `CONFLICT` — ran a same-category brand inside the window.
   - `CLEAR` — has confirmed history and no competing brand in the window.
   - `UNVERIFIED` — no confirmed sponsorship history to judge against.
3. **Scores geo leverage** (`src/geo.py`) from the share of audience in
   tier-one countries (US, GB, CA, AU) → `HIGH` / `MODERATE` / `LOW` with a
   one-line note.
4. **Combines** the above into one or two short negotiation bullets per
   creator (`src/screen.py`).
5. **Writes a color-coded XLSX** (`src/report.py`) with a frozen header:
   red = CONFLICT, green = CLEAR, amber = UNVERIFIED.

## Install

```bash
pip install -r requirements.txt
```

## Run (mock mode — no API key)

```bash
python run.py --brand CyberGhost --creators data/creators_sample.csv --out report.xlsx
```

### Options

| Flag          | Description                                          |
|---------------|------------------------------------------------------|
| `--brand`     | Target brand name, e.g. `CyberGhost` (required).     |
| `--creators`  | Path to a CSV with a `handle` column (required).     |
| `--out`       | Output XLSX path (default `conflict_report.xlsx`).   |
| `--live`      | Use the live Scrape Creators API (default: mock).    |

## Input CSV

A single `handle` column. See `data/creators_sample.csv`:

```csv
handle
techreviewerjane
gadgetguygreg
```

## Configuration

Edit `config.py` (data only, no logic):

- `LOOKBACK_MONTHS` — conflict window (default 12).
- `TIER_ONE_COUNTRIES` — `["US", "GB", "CA", "AU"]`.
- `BRAND_CATEGORY` — maps a brand to its category (e.g. `cyberghost → vpn`).
- `COMPETITOR_PATTERNS` — competitor name patterns per category.

To screen a new brand, add it to `BRAND_CATEGORY` (and, if it's a new
category, add competitor patterns).

## Going live

Mock mode is the default and needs no key. To use real data:

1. Open `src/scrape_client.py` and fill in the clearly-marked section in
   `_fetch_live` (there is exactly one spot to wire up).
2. Set your key: `export SCRAPE_CREATORS_API_KEY=...`
3. Run with `--live`:

```bash
python run.py --brand CyberGhost --creators data/creators_sample.csv --out report.xlsx --live
```

Live records are marked `verified=True` only for fields the API actually
returned; missing fields stay empty.
