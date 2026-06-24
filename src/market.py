"""Market intelligence: aggregate creator sponsorships into a brand-level map.

Given a set of fetched creator records (each carrying ``recent_sponsors``),
build a ranked table of brands that are actively sponsoring creators in the
niche — the brands you could pitch against, or learn from.

Honesty rules: we only count sponsors the API actually returned, never
invent placements, and only count placements inside the lookback window.
"""

from datetime import datetime, timedelta

import config

# Confidence ordering as returned by the sponsors endpoint. Anything the API
# doesn't rate (missing/unknown) sorts below "low" so the default medium
# threshold filters it out — we filter, we never relabel.
CONFIDENCE_LEVELS = ["low", "medium", "high"]
_CONFIDENCE_RANK = {level: i + 1 for i, level in enumerate(CONFIDENCE_LEVELS)}

# Obvious generic, non-brand phrases the sponsor detector sometimes emits.
# These are dropped (not relabeled) because they name no actual brand.
_GENERIC_PHRASES = {
    "needed", "vpn", "a vpn", "your vpn", "this vpn", "the vpn",
    "any vpn", "any vpn provider", "any service provider", "any provider",
    "sponsor", "sponsors", "today's sponsor", "todays sponsor",
}


def _confidence_rank(value):
    return _CONFIDENCE_RANK.get((value or "").strip().lower(), 0)


def _is_generic(name):
    """True for obvious non-brand phrases (explicit list + 'any ...' prefix)."""
    lowered = name.strip().lower()
    if lowered in _GENERIC_PHRASES:
        return True
    # "any X provider", "any VPN", etc. never name a real brand.
    return lowered.startswith("any ")


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


def aggregate_brands(records, months, min_confidence="medium"):
    """Aggregate sponsors across creator records into ranked brand rows.

    ``records`` is a list of creator record dicts (with ``recent_sponsors``).
    Only placements within ``months`` are counted. Sponsors rated below
    ``min_confidence`` (default "medium") and obvious generic non-brand
    phrases are filtered out — we only ever drop what the API returned, never
    invent or relabel.

    Returns ``(rows, stats)`` where rows are sorted by distinct creators
    (desc) then total placements (desc), each with:
      brand, distinct_creators, total_placements, most_recent_date,
      category ("unmapped" when unknown), example_handles (up to 3).
    ``stats`` reports how many sponsors were dropped: keys low_confidence,
    generic, total, and the min_confidence used.
    """
    min_rank = _CONFIDENCE_RANK.get((min_confidence or "medium").lower(), 2)
    brands = {}  # norm key -> aggregation dict
    dropped_low = 0
    dropped_generic = 0

    for record in records:
        handle = record.get("handle")
        for sponsor in record.get("recent_sponsors") or []:
            name = (sponsor.get("name") or "").strip()
            if not name:
                continue  # never invent a brand for a blank sponsor
            date = sponsor.get("date")
            if not _within_window(date, months):
                continue  # out-of-window isn't "noise", just not in scope

            # Drop obvious non-brand phrases.
            if _is_generic(name):
                dropped_generic += 1
                continue
            # Drop anything rated below the confidence threshold.
            if _confidence_rank(sponsor.get("confidence")) < min_rank:
                dropped_low += 1
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
    stats = {
        "low_confidence": dropped_low,
        "generic": dropped_generic,
        "total": dropped_low + dropped_generic,
        "min_confidence": (min_confidence or "medium").lower(),
    }
    return rows, stats
