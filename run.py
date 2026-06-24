#!/usr/bin/env python3
"""Screen creators against a target brand — or source new ones to spec.

Two modes:

  SCREEN (default) — screen a list of handles you already have:
    python run.py --brand CyberGhost --creators data/creators_sample.csv \\
        --out report.xlsx

  SOURCE (--source) — discover creators by topic, then screen them:
    python run.py --source --brand CyberGhost --query "vpn review" \\
        --limit 20 --out sourced.xlsx

By default both run in MOCK mode (clearly-labeled sample data, no API key
needed). Pass --live to use the real Scrape Creators API.
"""

import argparse
import csv
import sys
from collections import Counter

from src import report as report_mod
from src import screen as screen_mod
from src import scrape_client


def read_handles(csv_path):
    """Read creator handles from a CSV that has a 'handle' column."""
    handles = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None or "handle" not in reader.fieldnames:
            raise ValueError(
                f"{csv_path} must have a 'handle' column. "
                f"Found columns: {reader.fieldnames}"
            )
        for row in reader:
            handle = (row.get("handle") or "").strip()
            if handle:
                handles.append(handle)
    return handles


def parse_args(argv=None):
    p = argparse.ArgumentParser(
        description="Screen creators against a target brand, or source new "
        "ones by topic, with conflict / geo-leverage / negotiation notes."
    )
    p.add_argument("--brand", required=True, help="Target brand name (e.g. CyberGhost).")
    p.add_argument(
        "--source", action="store_true",
        help="Source mode: discover creators by --query instead of reading a CSV.",
    )
    p.add_argument(
        "--creators",
        help="(screen mode) Path to a CSV with a 'handle' column.",
    )
    p.add_argument(
        "--query",
        help="(source mode) Topic keyword to search YouTube channels for.",
    )
    p.add_argument(
        "--min-subs", type=int, default=None,
        help="(source mode) Drop candidates below this subscriber count.",
    )
    p.add_argument(
        "--max-subs", type=int, default=None,
        help="(source mode) Drop candidates above this subscriber count.",
    )
    p.add_argument(
        "--limit", type=int, default=20,
        help="(source mode) Max candidates to screen (default 20, controls spend).",
    )
    p.add_argument(
        "--out", default=None,
        help="Output XLSX path (defaults per mode).",
    )
    p.add_argument(
        "--live", action="store_true",
        help="Use the live Scrape Creators API (default: mock data).",
    )
    args = p.parse_args(argv)

    if args.source:
        if not args.query:
            p.error("--source requires --query (the topic keyword to search).")
    else:
        if not args.creators:
            p.error("screen mode requires --creators (or pass --source).")
    if args.out is None:
        args.out = "sourced_report.xlsx" if args.source else "conflict_report.xlsx"
    return args


def _print_result_line(label, result):
    flag = "verified" if result["verified"] else "unverified data"
    print(f"  {label}: {result['status']}  ({flag})")
    if result.get("conflict_reason"):
        print(f"      reason: {result['conflict_reason']}")
    for b in result["bullets"]:
        print(f"      - {b}")


def _summarize(results):
    counts = Counter(r["status"] for r in results)
    summary = ", ".join(f"{k}: {v}" for k, v in counts.items())
    print(f"Summary — {summary}")


def run_screen(args):
    """Screen mode: screen a CSV of handles already in hand."""
    mode = "LIVE" if args.live else "MOCK (sample data)"
    print(f"Screening for brand: {args.brand}")
    print(f"Mode: {mode}")
    print(f"Reading creators from: {args.creators}\n")

    handles = read_handles(args.creators)
    if not handles:
        print("No handles found in CSV.", file=sys.stderr)
        return 1

    results = []
    for handle in handles:
        record = scrape_client.fetch_creator(handle, live=args.live)
        result = screen_mod.screen_creator(record, args.brand)
        results.append(result)
        _print_result_line(handle, result)

    out_path = report_mod.write_report(results, args.out)
    print(f"\nWrote color-coded report to: {out_path}")
    _summarize(results)
    return 0


def run_source(args):
    """Source mode: discover candidates by topic, then run the existing screen."""
    mode = "LIVE" if args.live else "MOCK (sample data)"
    print(f"Sourcing creators for brand: {args.brand}")
    print(f"Mode: {mode}")
    print(f"Search query: {args.query!r}  | limit: {args.limit}")
    size = []
    if args.min_subs is not None:
        size.append(f">= {args.min_subs:,} subs")
    if args.max_subs is not None:
        size.append(f"<= {args.max_subs:,} subs")
    if size:
        print(f"Size filter: {' and '.join(size)}")
    print()

    # 1. Search for candidate channels (deduped, capped at limit).
    candidates = scrape_client.search_channels(args.query, args.limit, live=args.live)
    print(f"Found {len(candidates)} candidate channel(s) (after dedupe, capped at {args.limit}).")

    # Cost control: show the spend before any live channel lookups.
    if args.live:
        print(
            f"About to make {len(candidates)} live channel-detail lookup(s) "
            "(one per candidate), plus the search request(s) already spent.\n"
        )
    else:
        print()

    # 2. For each candidate: pull channel details, then run the EXISTING screen.
    results = []
    skipped = 0
    for c in candidates:
        handle = c["handle"]
        record = scrape_client.fetch_channel_profile(handle, live=args.live)
        result = screen_mod.screen_creator(record, args.brand)
        result["search_query"] = args.query

        # 3. Apply subscriber filters on the authoritative count. When the
        #    count is unknown (failed lookup / API didn't return it) we keep
        #    the candidate visible rather than silently dropping it.
        subs = result.get("subscribers")
        if subs is not None:
            if args.min_subs is not None and subs < args.min_subs:
                skipped += 1
                continue
            if args.max_subs is not None and subs > args.max_subs:
                skipped += 1
                continue

        results.append(result)
        label = f"{handle} ({subs:,} subs)" if isinstance(subs, int) else f"{handle} (subs n/a)"
        _print_result_line(label, result)

    if skipped:
        print(f"\n  ({skipped} candidate(s) filtered out by the subscriber size filter.)")

    if not results:
        print("\nNo candidates matched after filtering.", file=sys.stderr)
        return 1

    out_path = report_mod.write_report(results, args.out, include_source_columns=True)
    print(f"\nWrote color-coded report to: {out_path}")
    _summarize(results)
    return 0


def main(argv=None):
    args = parse_args(argv)
    if args.source:
        return run_source(args)
    return run_screen(args)


if __name__ == "__main__":
    sys.exit(main())
