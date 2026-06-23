"""Conflict screening: did a creator run a same-category brand recently?

Status values:
  - CONFLICT   : ran a competing brand inside the lookback window.
  - CLEAR      : has confirmed history, and no competing brand in window.
  - UNVERIFIED : no confirmed sponsorship history to judge against.
"""

from datetime import datetime, timedelta

import config

CONFLICT = "CONFLICT"
CLEAR = "CLEAR"
UNVERIFIED = "UNVERIFIED"


def _within_window(date_str, months):
    """True if date_str (YYYY-MM-DD) is within the last `months` months."""
    if not date_str:
        return False
    try:
        when = datetime.strptime(date_str, "%Y-%m-%d")
    except (ValueError, TypeError):
        return False
    cutoff = datetime.utcnow() - timedelta(days=30 * months)
    return when >= cutoff


def _matches_competitor(sponsor, category):
    """True if the sponsor looks like a competitor in `category`."""
    patterns = config.competitor_patterns_for_category(category)
    name = (sponsor.get("name") or "").lower()
    sponsor_category = (sponsor.get("category") or "").lower()
    # A category match on the sponsor record is the strongest signal.
    if sponsor_category and sponsor_category == category:
        return True
    # Otherwise fall back to name pattern matching.
    return any(p in name for p in patterns)


def screen_conflict(record, brand):
    """Screen one creator record against the target brand.

    Returns a dict: {status, category, matched_sponsors, reason}.
    """
    category = config.category_for_brand(brand)
    months = config.LOOKBACK_MONTHS

    # A failed live lookup (401/402/network/etc.) leaves a short reason on the
    # record. We can't judge conflict from data we never got, so report
    # UNVERIFIED and surface the reason.
    if record.get("error"):
        return {
            "status": UNVERIFIED,
            "category": category,
            "matched_sponsors": [],
            "reason": record["error"],
        }

    if category is None:
        return {
            "status": UNVERIFIED,
            "category": None,
            "matched_sponsors": [],
            "reason": (
                f"No category mapping for brand '{brand}' in config; "
                "cannot screen for competitors."
            ),
        }

    sponsors = record.get("recent_sponsors") or []

    # No confirmed sponsorship history -> we can't say CLEAR honestly.
    if not sponsors:
        return {
            "status": UNVERIFIED,
            "category": category,
            "matched_sponsors": [],
            "reason": "No confirmed sponsorship history to screen against.",
        }

    matched = []
    for s in sponsors:
        if _matches_competitor(s, category) and _within_window(s.get("date"), months):
            matched.append(s)

    if matched:
        names = ", ".join(
            f"{m.get('name')} ({m.get('date')})" for m in matched
        )
        return {
            "status": CONFLICT,
            "category": category,
            "matched_sponsors": matched,
            "reason": f"Ran competing {category} brand(s) in last {months}mo: {names}.",
        }

    return {
        "status": CLEAR,
        "category": category,
        "matched_sponsors": [],
        "reason": f"No competing {category} brand in last {months} months.",
    }
