"""Geo leverage: score tier-one audience share into negotiation leverage.

Higher tier-one (US/GB/CA/AU) audience share generally means a creator's
audience is more valuable to a Western brand, which strengthens the brand's
interest — captured here as HIGH / MODERATE / LOW leverage with a short note.
"""

import config

HIGH = "HIGH"
MODERATE = "MODERATE"
LOW = "LOW"
UNKNOWN = "UNKNOWN"

# Thresholds on combined tier-one audience percentage.
HIGH_THRESHOLD = 60
MODERATE_THRESHOLD = 30


def tier_one_share(audience_geo):
    """Sum the audience percentage across tier-one countries."""
    if not audience_geo:
        return None
    return sum(
        pct for cc, pct in audience_geo.items()
        if cc.upper() in config.TIER_ONE_COUNTRIES
    )


def score_geo(record):
    """Return {leverage, tier_one_pct, note} for a creator record."""
    share = tier_one_share(record.get("audience_geo"))

    if share is None:
        return {
            "leverage": UNKNOWN,
            "tier_one_pct": None,
            "note": "No audience geo data available.",
        }

    if share >= HIGH_THRESHOLD:
        leverage = HIGH
        note = f"{share:.0f}% tier-one audience — strong fit, lead with value."
    elif share >= MODERATE_THRESHOLD:
        leverage = MODERATE
        note = f"{share:.0f}% tier-one audience — solid reach, negotiate on CPM."
    else:
        leverage = LOW
        note = f"Only {share:.0f}% tier-one audience — push for lower rate."

    return {"leverage": leverage, "tier_one_pct": share, "note": note}
