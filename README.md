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

## Three modes

- **Screen** (default) — screen a list of handles you already have.
- **Source** (`--source`) — discover creators by topic, then screen them.
- **Market** (`--market`) — map which brands sponsor creators in a niche.

All run in mock mode by default; add `--live` for the real API.

## Screen mode (mock — no API key)

```bash
python run.py --brand CyberGhost --creators data/creators_sample.csv --out report.xlsx
```

| Flag          | Description                                          |
|---------------|------------------------------------------------------|
| `--brand`     | Target brand name, e.g. `CyberGhost` (required).     |
| `--creators`  | Path to a CSV with a `handle` column (required).     |
| `--out`       | Output XLSX path (default `conflict_report.xlsx`).   |
| `--live`      | Use the live Scrape Creators API (default: mock).    |

## Source mode — find creators to spec

```bash
python run.py --source --brand CyberGhost --query "vpn review" --limit 20 --out sourced.xlsx
```

It searches YouTube channels for `--query`, dedupes them, and for each
candidate (up to `--limit`) pulls channel details — name, subscriber count,
and the channel's **own stated country** — then runs the **same** conflict
screen against `--brand`. Output is the same color-coded XLSX plus a
**Search Query** column and a **Channel Country (stated, not audience)**
column.

| Flag          | Description                                                       |
|---------------|------------------------------------------------------------------|
| `--source`    | Enable source mode.                                              |
| `--brand`     | Target brand name (required).                                    |
| `--query`     | Topic keyword to search channels for (required).                |
| `--min-subs`  | Drop candidates below this subscriber count (optional).         |
| `--max-subs`  | Drop candidates above this subscriber count (optional).         |
| `--limit`     | Max candidates to screen — default **20**, controls spend.       |
| `--out`       | Output XLSX path (default `sourced_report.xlsx`).               |
| `--live`      | Use the live Scrape Creators API (default: mock).               |

**Cost control:** source mode makes exactly **one channel lookup per
candidate**, and in `--live` mode it prints how many lookups it's about to
make before spending. Candidates outside the `--min-subs`/`--max-subs` range
are dropped (candidates whose count is unknown stay visible).

**Source mode is a cheap discovery pass:** it pulls channel identity + country
but does **not** fetch each candidate's full sponsor history, so the conflict
screen reports them **UNVERIFIED** (no confirmed sponsorships to judge). Take
the shortlist and run **screen mode `--live`** on it for full
CONFLICT / CLEAR verdicts. As always, `audience_geo` is never invented, so
**Leverage stays UNKNOWN** — Channel Country is the channel's stated country,
not audience location.

## Market mode — which brands are sponsoring a niche

```bash
python run.py --market --query "vpn review" --limit 15 --videos-per-creator 10 --out market.xlsx
# or scan a list you already have:
python run.py --market --creators data/creators_sample.csv --out market.xlsx
```

Gathers creators (search via `--query`, deduped, **or** a `--creators` CSV),
pulls each one's recent uploads within `--months` and their sponsors, then
aggregates everything into a ranked **brand-level** market map: brand, number
of distinct creators running it, total placements, most recent placement date,
the category it maps to in `config.py` (or `unmapped`), and up to 3 example
creator handles. Sorted by distinct creators (desc), then total placements.
Rows are color-coded green (maps to a known category) or amber (unmapped).

| Flag                   | Description                                                  |
|------------------------|--------------------------------------------------------------|
| `--market`             | Enable market mode.                                         |
| `--query`              | Topic to search creators for (or use `--creators`).        |
| `--creators`           | CSV of handles to scan (or use `--query`).                 |
| `--limit`              | Max creators to scan — default **15**.                     |
| `--videos-per-creator` | Max recent uploads scanned per creator — default **10**.   |
| `--months`             | Lookback window — default **12**.                          |
| `--out`                | Output XLSX path (default `market_report.xlsx`).           |
| `--live`               | Use the live Scrape Creators API (default: mock).          |

**Cost control (this is the heaviest job):** before any live calls it prints
the exact planned spend — `creators × videos-per-creator` video-sponsor
lookups, plus the per-creator channel/uploads lookups and the search — and the
`--limit` / `--videos-per-creator` caps bound it hard. A creator whose lookup
fails is marked UNVERIFIED, counted in the skipped tally, and never crashes the
batch. Only sponsors the API actually returned are counted; nothing is
invented. Note the live `suspectedSponsors` field can be noisy (it sometimes
returns generic phrases like "any VPN provider"); the map reflects exactly what
the API returned.

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
