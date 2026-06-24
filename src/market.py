"""Market intelligence: aggregate creator sponsorships into a brand-level map.

Given a set of fetched creator records (each carrying ``recent_sponsors``),
build a ranked table of brands that are actively sponsoring creators in the
niche — the brands you could pitch against, or learn from.

Honesty rules: we only count sponsors the API actually returned, never
invent placements, and only count placements inside the lookback window.
"""

from datetime import datetime, timedelta

import config


def _norm_key(name):
    """Normalize a brand name for grouping: lowercase, alphanumeric only.

    This merges obvious spelling variants ("Proton VPN" / "Protonvpn") while
    keeping genuinely different brands apart. We never merge across different
    alphanumeric content.
    """
    return "".join(ch for ch in name.lower() if ch.isalnum())


def _within_window(date_str, months):
    if not date_str:
        return False
    try:
        when = datetime.strptime(date_str, "%Y-%m-%d")
    except (ValueError, TypeError):
        return False
    return when >= datetime.utcnow() - timedelta(days=30 * months)


def aggregate_brands(records, months):
    """Aggregate sponsors across creator records into ranked brand rows.

    ``records`` is a list of creator record dicts (with ``recent_sponsors``).
    Only placements within ``months`` are counted.

    Returns a list of dicts sorted by distinct creators (desc) then total
    placements (desc), each with:
      brand, distinct_creators, total_placements, most_recent_date,
      category ("unmapped" when unknown), example_handles (up to 3).
    """
    brands = {}  # norm key -> aggregation dict

    for record in records:
        handle = record.get("handle")
        for sponsor in record.get("recent_sponsors") or []:
            name = (sponsor.get("name") or "").strip()
            if not name:
                continue  # never invent a brand for a blank sponsor
            date = sponsor.get("date")
            if not _within_window(date, months):
                continue

            key = _norm_key(name)
            if not key:
                continue
            entry = brands.get(key)
            if entry is None:
                entry = {
                    "display_counts": {},      # original spelling -> count
                    "creators": set(),
                    "placements": 0,
                    "most_recent_date": None,
                    "examples": [],            # ordered, distinct handles
                }
                brands[key] = entry

            entry["display_counts"][name] = entry["display_counts"].get(name, 0) + 1
            entry["placements"] += 1
            if handle:
                entry["creators"].add(handle)
                if handle not in entry["examples"] and len(entry["examples"]) < 3:
                    entry["examples"].append(handle)
            if date and (entry["most_recent_date"] is None or date > entry["most_recent_date"]):
                entry["most_recent_date"] = date

    rows = []
    for entry in brands.values():
        # Display the most frequently seen original spelling.
        display = max(entry["display_counts"].items(), key=lambda kv: kv[1])[0]
        category = config.category_for_sponsor(display)
        rows.append({
            "brand": display,
            "distinct_creators": len(entry["creators"]),
            "total_placements": entry["placements"],
            "most_recent_date": entry["most_recent_date"] or "",
            "category": category or "unmapped",
            "example_handles": ", ".join(entry["examples"]),
        })

    rows.sort(
        key=lambda r: (r["distinct_creators"], r["total_placements"]),
        reverse=True,
    )
    return rows
