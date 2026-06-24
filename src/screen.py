"""Combine conflict + geo into a screened result with negotiation bullets."""

from src import conflict as conflict_mod
from src import geo as geo_mod


def _negotiation_bullets(record, conflict_result, geo_result):
    """Produce one or two short, actionable negotiation bullets."""
    bullets = []
    status = conflict_result["status"]

    if status == conflict_mod.CONFLICT:
        bullets.append(
            "Conflict: " + conflict_result["reason"]
            + " Confirm exclusivity has lapsed before proceeding."
        )
    elif status == conflict_mod.CLEAR:
        bullets.append(
            "Clear on category — no competing deals on record; "
            "open with standard terms."
        )
    else:  # UNVERIFIED
        bullets.append(
            "Unverified history — request a sponsorship disclosure before "
            "committing to exclusivity terms."
        )

    # Second bullet from geo leverage, if we have it.
    if geo_result["leverage"] != geo_mod.UNKNOWN:
        bullets.append(f"{geo_result['leverage']} leverage — {geo_result['note']}")

    return bullets[:2]


def screen_creator(record, brand):
    """Screen one creator record and return a combined result dict."""
    conflict_result = conflict_mod.screen_conflict(record, brand)
    geo_result = geo_mod.score_geo(record)
    bullets = _negotiation_bullets(record, conflict_result, geo_result)

    return {
        "handle": record.get("handle"),
        "name": record.get("name"),
        "platform": record.get("platform"),
        "subscribers": record.get("subscribers"),
        "verified": record.get("verified", False),
        "source": record.get("source"),
        "channel_country": record.get("channel_country"),
        "status": conflict_result["status"],
        "category": conflict_result["category"],
        "conflict_reason": conflict_result["reason"],
        "tier_one_pct": geo_result["tier_one_pct"],
        "leverage": geo_result["leverage"],
        "geo_note": geo_result["note"],
        "bullets": bullets,
    }
