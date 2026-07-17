# Creator–Brand Research & Conflict-Screening Toolkit

A command-line toolkit that automates influencer-marketing research by pulling live creator and sponsorship data from the Scrape Creators API and turning it into structured, decision-ready reports. Built and operated through Claude Code.

It answers questions that normally take hours of manual scrolling: *Which brands are actively sponsoring creators in a given niche? Has a creator run a competing brand recently? Which creators fit a specific campaign brief?* — and returns the answers as clean spreadsheets, with every unverified data point flagged rather than guessed.

## What it does

The toolkit runs in six modes from a single CLI (run.py):

| Mode | Flag | What it produces |
|------|------|------------------|
| Screen | --screen | Conflict check — flags any creator who has run a competing brand inside a 12-month window (GREEN safe / RED conflict / YELLOW unverified) |
| Source | --source | Finds creators to spec, with hard subscriber-range filtering |
| Market | --market | Brand intelligence — which brands sponsor creators in a given niche |
| Radar | --radar | Multi-platform brand radar across a creator roster, with reachability tiering and category tagging |
| Draft | --draft | Generates a first-touch outreach email for a target brand |
| Sequence | --sequence | Builds a full multi-touch follow-up sequence |

## How it works

- Language: Python
- Data source: Scrape Creators REST API (authenticated via x-api-key header), pulling creator profiles, video metadata, and paid-partnership signals across YouTube and Instagram
- Environment: Runs inside Claude Code, which handles orchestration, iteration, and report generation
- Output: Structured .xlsx reports with a consistent schema per mode

A spend gate prints the planned number of API lookups and waits for approval before any large scan runs, so cost stays controlled.

## Data integrity

The core design rule is no fabrication. Every field the API can confirm is marked verified; anything it cannot confirm is labeled UNVERIFIED rather than filled with a plausible guess. Corroboration is tracked explicitly — a brand mentioned by one creator is tagged differently from one confirmed across several — so downstream decisions rest on real signal, not noise.

## Running it

export SCRAPECREATORS_API_KEY=your_key_here

python run.py --screen --brand "BrandName" --creators creators.csv

python run.py --radar --roster roster.csv --platforms youtube

Input is a simple CSV (handle, tags); output lands as an .xlsx report.

## Why I built it

Influencer-marketing research is repetitive, easy to get wrong, and slow to do by hand. This toolkit turns a manual research process into a repeatable, auditable pipeline — one that scales across hundreds of creators while keeping a human in the loop on cost and on any data it can't verify.
