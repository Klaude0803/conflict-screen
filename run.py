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

from src import market as market_mod
from src import outreach as outreach_mod
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
    p.add_argument(
        "--brand",
        help="Target brand name, e.g. CyberGhost (required for screen/source modes).",
    )
    p.add_argument(
        "--source", action="store_true",
        help="Source mode: discover creators by --query instead of reading a CSV.",
    )
    p.add_argument(
        "--market", action="store_true",
        help="Market mode: map which brands sponsor creators in a niche.",
    )
    p.add_argument(
        "--radar", action="store_true",
        help="Radar mode: multi-platform brand radar with gambling exclusion, "
             "live/evergreen tags, and roster conflict/fit (the football brief).",
    )
    p.add_argument(
        "--roster",
        help="(radar mode) CSV: each row a creator handle plus comma-separated niche tags.",
    )
    p.add_argument(
        "--platforms", default="youtube",
        help="(radar mode) Comma-separated platforms: youtube,tiktok,instagram.",
    )
    p.add_argument(
        "--plan-only", action="store_true",
        help="(radar mode) Print the planned live lookup count and exit (no spend).",
    )
    p.add_argument(
        "--draft", action="store_true",
        help="Draft mode: write a cold-email DRAFT to a brand (never sends).",
    )
    p.add_argument(
        "--sequence", action="store_true",
        help="(draft mode) Write a six-touch follow-up sequence DRAFT instead "
             "of a single email.",
    )
    p.add_argument(
        "--creators",
        help="(screen/market) CSV path with a 'handle' column; "
             "(draft) comma-separated example handles for the brand.",
    )
    p.add_argument(
        "--category",
        help="(draft mode) The brand's category, from the market radar.",
    )
    p.add_argument(
        "--recent",
        help="(draft mode) Most recent placement date, from the market radar.",
    )
    p.add_argument(
        "--market-csv",
        help="(draft mode) Optional market-radar CSV to auto-pull the brand row.",
    )
    p.add_argument(
        "--query",
        help="(source/market mode) Topic keyword to search YouTube channels for.",
    )
    p.add_argument(
        "--videos-per-creator", type=int, default=10,
        help="(market mode) Max recent uploads to scan per creator (default 10).",
    )
    p.add_argument(
        "--months", type=int, default=12,
        help="(market mode) Lookback window in months (default 12).",
    )
    p.add_argument(
        "--min-confidence", choices=market_mod.CONFIDENCE_LEVELS, default="medium",
        help="(market mode) Lowest sponsor confidence to count (default medium; "
             "use low for the raw, unfiltered view).",
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

    # --sequence is a draft-mode variant; enable draft mode if it's passed.
    if args.sequence:
        args.draft = True

    if sum(bool(m) for m in (args.source, args.market, args.draft, args.radar)) > 1:
        p.error("choose one mode: --source, --market, --radar, or --draft.")

    if args.radar:
        if not (args.query or args.roster):
            p.error("--radar requires --query and/or --roster.")
    elif args.draft:
        if not args.brand:
            p.error("--draft requires --brand.")
    elif args.market:
        if not (args.query or args.creators):
            p.error("--market requires --query or --creators.")
    elif args.source:
        if not args.brand:
            p.error("--source requires --brand.")
        if not args.query:
            p.error("--source requires --query (the topic keyword to search).")
    else:
        if not args.brand:
            p.error("screen mode requires --brand.")
        if not args.creators:
            p.error("screen mode requires --creators (or pass --source/--market).")

    if args.out is None:
        if args.draft:
            slug = "".join(c for c in args.brand.lower() if c.isalnum()) or "brand"
            args.out = f"sequence_{slug}.txt" if args.sequence else f"draft_{slug}.txt"
        elif args.market:
            args.out = "market_report.xlsx"
        elif args.radar:
            args.out = "radar_report.xlsx"
        elif args.source:
            args.out = "sourced_report.xlsx"
        else:
            args.out = "conflict_report.xlsx"
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


def _gather_handles(args):
    """Get the creator handles to scan (from --query search or --creators CSV).

    Returns (handles, used_search) where used_search marks whether a live
    search request was spent during gathering.
    """
    if args.query:
        candidates = scrape_client.search_channels(args.query, args.limit, live=args.live)
        return [c["handle"] for c in candidates], True
    handles = read_handles(args.creators)[:args.limit]
    return handles, False


def run_market(args):
    """Market mode: map which brands sponsor creators across a niche."""
    mode = "LIVE" if args.live else "MOCK (sample data)"
    source_desc = f"query {args.query!r}" if args.query else f"CSV {args.creators}"
    print(f"Market map for brand niche via {source_desc}")
    print(f"Mode: {mode}")
    print(f"Caps — creators: {args.limit}, videos/creator: {args.videos_per_creator}, "
          f"lookback: {args.months}mo\n")

    # 1. Gather creators (deduped by search, or from the CSV), capped at limit.
    handles, used_search = _gather_handles(args)
    print(f"Gathered {len(handles)} creator(s) to scan (capped at {args.limit}).")

    # 2. Cost control: show the exact planned spend BEFORE the heavy calls.
    planned_sponsor_lookups = len(handles) * args.videos_per_creator
    if args.live:
        search_note = "1 search (already spent)" if used_search else "no search"
        print(
            "Planned live spend: "
            f"{len(handles)} creators x {args.videos_per_creator} videos = "
            f"{planned_sponsor_lookups} video-sponsor lookups, plus {len(handles)} "
            f"channel + channel-videos lookups, plus {search_note}.\n"
        )
    else:
        print()

    # 3. Pull each creator's recent uploads + sponsors (bounded by the caps).
    records = []
    skipped = 0
    for handle in handles:
        record = scrape_client.fetch_creator(
            handle, live=args.live,
            months=args.months, max_videos=args.videos_per_creator,
        )
        if record.get("error"):
            # Failed lookup -> UNVERIFIED, count as skipped, keep going.
            skipped += 1
            print(f"  {handle}: UNVERIFIED (skipped) — {record['error']}")
            continue
        n = len(record.get("recent_sponsors") or [])
        records.append(record)
        print(f"  {handle}: {n} sponsor placement(s) found")

    # 4. Aggregate into the ranked brand table (with the confidence filter).
    rows, stats = market_mod.aggregate_brands(
        records, args.months, min_confidence=args.min_confidence,
    )

    print(f"\nScanned {len(records)} creator(s); {skipped} skipped (failed lookup).")
    print(
        f"Filter (min-confidence={stats['min_confidence']}): dropped "
        f"{stats['total']} sponsor mention(s) "
        f"({stats['low_confidence']} below confidence, {stats['generic']} generic, "
        f"{stats['self_reference']} channel self-reference)."
    )
    if not rows:
        print("No sponsors left after filtering — nothing to rank.")
        # Still write an (empty) report so the run is reproducible.
        out_path = report_mod.write_market_report(rows, args.out)
        print(f"Wrote market map to: {out_path}")
        return 0

    print(f"\nRanked brands ({len(rows)}):")
    print(f"  {'BRAND':<24} {'CREATORS':>8} {'PLACEMENTS':>10} {'CATEGORY':<16} RECENT")
    for r in rows:
        print(f"  {r['brand']:<24} {r['distinct_creators']:>8} "
              f"{r['total_placements']:>10} {r['category']:<16} {r['most_recent_date']}")

    out_path = report_mod.write_market_report(rows, args.out)
    print(f"\nWrote color-coded market map to: {out_path}")
    return 0


def _row_from_market_csv(path, brand):
    """Pull a brand's row from a market-radar CSV (lenient on column names).

    Returns (category, recent, [handles]) or (None, None, []) if not found.
    """
    want = brand.strip().lower()
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        # Map headers case-insensitively / loosely to the fields we need.
        def find_col(*needles):
            for col in reader.fieldnames or []:
                low = col.lower()
                if all(n in low for n in needles):
                    return col
            return None

        brand_col = find_col("brand")
        cat_col = find_col("category")
        recent_col = find_col("recent")
        ex_col = find_col("example")
        for row in reader:
            if brand_col and (row.get(brand_col) or "").strip().lower() == want:
                category = (row.get(cat_col) or "").strip() if cat_col else None
                recent = (row.get(recent_col) or "").strip() if recent_col else None
                examples = (row.get(ex_col) or "") if ex_col else ""
                handles = [h.strip() for h in examples.split(",") if h.strip()]
                return category or None, recent or None, handles
    return None, None, []


# A built-in sample row so draft mode works out of the box (mock).
_SAMPLE_DRAFT_ROW = {
    "category": "vpn",
    "recent": "2026-06-25",
    "creators": ["securitysam", "vpnvinny"],
}


def run_draft(args):
    """Draft mode: write a cold-email DRAFT to a brand. Never sends anything."""
    print(f"Drafting outreach for brand: {args.brand}")
    print("Mode: DRAFT ONLY — nothing is sent, no email integration.\n")

    category, recent, creators = args.category, args.recent, []
    if args.creators:
        creators = [h.strip() for h in args.creators.split(",") if h.strip()]

    # Optionally auto-pull the row from a market-radar CSV.
    if args.market_csv:
        csv_cat, csv_recent, csv_handles = _row_from_market_csv(args.market_csv, args.brand)
        category = category or csv_cat
        recent = recent or csv_recent
        creators = creators or csv_handles
        if csv_cat or csv_recent or csv_handles:
            print(f"Pulled '{args.brand}' row from {args.market_csv}.")
        else:
            print(f"Note: '{args.brand}' not found in {args.market_csv}; using flags/sample.")

    # Fall back to the sample row so mock mode always works.
    used_sample = False
    if not (category or recent or creators):
        category = _SAMPLE_DRAFT_ROW["category"]
        recent = _SAMPLE_DRAFT_ROW["recent"]
        creators = list(_SAMPLE_DRAFT_ROW["creators"])
        used_sample = True
        print("No row details supplied; using the built-in SAMPLE brand row.")

    if args.sequence:
        seq = outreach_mod.build_sequence(
            args.brand, category=category, recent=recent, creators=creators,
        )
        out_path = outreach_mod.write_sequence(
            seq, args.out, category=category, recent=recent, creators=creators,
        )
        print()
        print(outreach_mod.render_sequence_text(
            seq, category=category, recent=recent, creators=creators,
        ))
    else:
        draft = outreach_mod.build_draft(
            args.brand, category=category, recent=recent, creators=creators,
        )
        out_path = outreach_mod.write_draft(
            draft, args.out, category=category, recent=recent, creators=creators,
        )
        print()
        print(outreach_mod.render_draft_text(
            draft, category=category, recent=recent, creators=creators,
        ))
    if used_sample:
        print("\n(Generated from SAMPLE data.)")
    print(f"\nWrote DRAFT to: {out_path}  (review before sending — not sent)")
    return 0


def _read_roster(path):
    """Read a roster CSV: each row a handle plus comma-separated niche tags.

    Accepts either a 2-column 'handle,tags' file or a row where the first cell
    is the handle and the rest are tags. Returns {handle: [tags]}.
    """
    roster = {}
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        for row in reader:
            cells = [c.strip() for c in row if c is not None]
            cells = [c for c in cells if c != ""]
            if not cells:
                continue
            handle = cells[0].lstrip("@")
            if handle.lower() in ("handle", "creator"):
                continue  # header row
            tags = []
            for c in cells[1:]:
                tags += [t.strip() for t in c.split(",") if t.strip()]
            roster[handle] = tags
    return roster


# Per-creator live lookup cost by platform (for the planned-spend estimate).
def _per_creator_lookups(platform, videos_per_creator):
    platform = platform.lower()
    if platform in ("youtube", "yt"):
        # 1 channel + ~1 channel-videos page + up to N video-sponsor calls.
        return 2 + videos_per_creator
    if platform in ("instagram", "ig"):
        return 2  # up to a couple of posts pages
    if platform in ("tiktok", "tt"):
        return 1  # one profile call
    return 1


def run_radar(args):
    """Radar mode: multi-platform brand radar for the football brief."""
    mode = "LIVE" if args.live else "MOCK (sample data)"
    platforms = [p.strip() for p in args.platforms.split(",") if p.strip()]
    queries = [q.strip() for q in (args.query or "").split(",") if q.strip()]
    roster = _read_roster(args.roster) if args.roster else {}
    scan_months, conflict_months = args.months, 12

    print("Football brand radar")
    print(f"Mode: {mode}")
    print(f"Platforms: {', '.join(platforms)}")
    print(f"Queries: {queries or '(roster only)'}")
    print(f"Roster: {len(roster)} creator(s) | scan window: {scan_months}mo | "
          f"conflict window: {conflict_months}mo")
    print(f"Caps — creators/platform: {args.limit}, videos/creator: "
          f"{args.videos_per_creator}, min-confidence: {args.min_confidence}\n")

    # --- Cost control: print the exact planned live lookups. ----------------
    # Per-platform creators = roster handles + up to --limit search results.
    planned_creators = {}
    for pf in platforms:
        planned_creators[pf] = min(args.limit, args.limit) + len(roster)
    search_calls = sum(len(queries) for _ in platforms)
    fetch_calls = sum(
        planned_creators[pf] * _per_creator_lookups(pf, args.videos_per_creator)
        for pf in platforms
    )
    total_planned = search_calls + fetch_calls
    print("PLANNED LIVE LOOKUPS (upper bound):")
    for pf in platforms:
        per = _per_creator_lookups(pf, args.videos_per_creator)
        print(f"  {pf}: {len(queries)} search + {planned_creators[pf]} creators x "
              f"~{per} lookups = ~{len(queries) + planned_creators[pf]*per}")
    print(f"  TOTAL upper bound: ~{total_planned} live lookups "
          f"(search {search_calls} + per-creator {fetch_calls}).")
    if args.plan_only:
        print("\n--plan-only set: stopping before any live calls. No spend.")
        return 0
    print()

    # --- Gather creators per platform (roster + deduped search). -----------
    to_fetch = []  # (handle, platform, is_roster)
    for pf in platforms:
        seen = set()
        for h in roster:
            seen.add(h.lower())
            to_fetch.append((h, pf, True))
        if queries and (args.live or True):
            picked = 0
            for q in queries:
                for c in scrape_client.radar_search(q, pf, args.limit, live=args.live):
                    hl = c["handle"].lower().lstrip("@")
                    if hl in seen:
                        continue
                    seen.add(hl)
                    to_fetch.append((c["handle"], pf, False))
                    picked += 1
                    if picked >= args.limit:
                        break
                if picked >= args.limit:
                    break
    print(f"Gathered {len(to_fetch)} (creator, platform) pairs to scan.\n")

    # --- Fetch each creator's sponsors on its platform. --------------------
    records, skipped = [], 0
    for handle, pf, is_roster in to_fetch:
        months = conflict_months if is_roster else scan_months
        rec = scrape_client.radar_fetch(
            handle, pf, live=args.live, months=months,
            max_videos=args.videos_per_creator,
        )
        if rec.get("error"):
            skipped += 1
            print(f"  {handle} [{pf}]: UNVERIFIED (skipped) — {rec['error']}")
            continue
        records.append(rec)
        n = len(rec.get("recent_sponsors") or [])
        print(f"  {handle} [{rec.get('platform')}]: {n} sponsor placement(s)")

    # --- Aggregate into the radar table. -----------------------------------
    rows, review, stats = market_mod.aggregate_radar(
        records, scan_months=scan_months, conflict_months=conflict_months,
        roster=roster, min_confidence=args.min_confidence,
    )

    print(f"\nScanned {len(records)} creator-platform record(s); {skipped} skipped.")
    print(f"Dropped: {stats['gambling']} gambling (hard), "
          f"{stats['low_confidence']} below confidence, {stats['generic']} generic, "
          f"{stats['self_reference']} self-reference.")

    if rows:
        print(f"\nRanked brands ({len(rows)}) — LIKELY DIRECT first:")
        hdr = (f"  {'BRAND':<17}{'REACHABILITY':<16}{'CATEGORY':<24}"
               f"{'PLATFORM':<20}{'TAG':<20}{'CONFLICT':<22}RECENT")
        print(hdr)
        for r in rows:
            print(f"  {r['brand'][:16]:<17}{r['reachability']:<16}"
                  f"{r['brief_category'][:23]:<24}{r['platforms'][:19]:<20}"
                  f"{r['recency_tag'][:19]:<20}{r['roster_conflict'][:21]:<22}"
                  f"{r['most_recent_date']}")
    else:
        print("\nNo brands surfaced after exclusions and filtering.")

    if review:
        print(f"\nEXCLUDED FOR REVIEW ({len(review)} borderline name(s)):")
        for x in review:
            print(f"  {x['brand']}: {x['reason']}")

    out_path = report_mod.write_radar_report(rows, args.out, excluded_for_review=review)
    print(f"\nWrote radar report to: {out_path}")
    return 0


def main(argv=None):
    args = parse_args(argv)
    if args.radar:
        return run_radar(args)
    if args.draft:
        return run_draft(args)
    if args.market:
        return run_market(args)
    if args.source:
        return run_source(args)
    return run_screen(args)


if __name__ == "__main__":
    sys.exit(main())
