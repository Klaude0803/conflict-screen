#!/usr/bin/env python3
"""Screen a list of creators against a target brand.

Usage:
    python run.py --brand CyberGhost --creators data/creators_sample.csv \\
        --out report.xlsx

By default it runs in MOCK mode (clearly-labeled sample data, no API key
needed). Pass --live to use the real Scrape Creators API once it's wired up.
"""

import argparse
import csv
import sys

from src import report as report_mod
from src import screen as screen_mod
from src.scrape_client import fetch_creator


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
        description="Screen creators against a target brand for conflicts, "
        "geo leverage, and negotiation notes."
    )
    p.add_argument("--brand", required=True, help="Target brand name (e.g. CyberGhost).")
    p.add_argument(
        "--creators", required=True,
        help="Path to a CSV with a 'handle' column.",
    )
    p.add_argument(
        "--out", default="conflict_report.xlsx",
        help="Output XLSX path (default: conflict_report.xlsx).",
    )
    p.add_argument(
        "--live", action="store_true",
        help="Use the live Scrape Creators API (default: mock data).",
    )
    return p.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
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
        record = fetch_creator(handle, live=args.live)
        result = screen_mod.screen_creator(record, args.brand)
        results.append(result)

        flag = "verified" if result["verified"] else "UNVERIFIED data"
        print(f"  {handle}: {result['status']}  ({flag})")
        for b in result["bullets"]:
            print(f"      - {b}")

    out_path = report_mod.write_report(results, args.out)
    print(f"\nWrote color-coded report to: {out_path}")

    # Quick summary counts.
    from collections import Counter
    counts = Counter(r["status"] for r in results)
    summary = ", ".join(f"{k}: {v}" for k, v in counts.items())
    print(f"Summary — {summary}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
