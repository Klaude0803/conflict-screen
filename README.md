# Creator–Brand Research & Conflict-Screening Toolkit

## Current implementation

Start with [RESEARCH.md](RESEARCH.md) for the new cached, credit-bounded research layer and all 13 pinned ScrapeCreators playbooks. Repository-based agents follow [AGENTS.md](AGENTS.md).

```sh
python -m src.research skills
python -m src.research plan --mode creator --handle AndrewGold --out private-research/plan.json
python -m unittest discover -s tests -v
```

Executable research supports bounded YouTube profiles, recent-upload metrics, latest public captions, sponsor candidates, observed related-video discovery and competitor data packets. The playbooks support further analysis of supplied evidence across platforms. ChatGPT or the interactive agent interprets the data; no paid AI generation is invoked.

`src.outreach` prepares review-only outreach payloads with sender and timezone checks. Live collection needs a separately accepted ScrapeCreators credit allowance. The existing Make/Google Sheets workflow handles Gmail drafts and user-approved sending; GitHub code does not send emails or run automatically in Make.

The legacy `run.py` screening command still uses mock data by default, and its live conflict client remains unimplemented. The six modes described below are the original roadmap, not six implemented CLI flags. Partial public sponsorship scans must never be treated as proof a creator is conflict free.

## Original roadmap

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
