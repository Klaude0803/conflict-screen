"""Central configuration for the creator conflict screener.

Everything here is data, not logic. Adjust the lookback window, the
tier-one country list, the brand -> category mapping, and the competitor
patterns without touching the screening code.
"""

# How far back we consider a sponsorship "recent" enough to matter.
LOOKBACK_MONTHS = 12

# Tier-one audience markets. A large share of audience in these countries
# generally means stronger negotiation leverage for a brand deal.
TIER_ONE_COUNTRIES = ["US", "GB", "CA", "AU"]

# Map a target brand (lowercased on lookup) to the category it competes in.
# A creator who has run a brand in the SAME category is a conflict.
BRAND_CATEGORY = {
    "cyberghost": "vpn",
    "nordvpn": "vpn",
    "expressvpn": "vpn",
    "surfshark": "vpn",
    "protonvpn": "vpn",
    "squarespace": "website_builder",
    "wix": "website_builder",
    "hellofresh": "meal_kit",
    "factor": "meal_kit",
    "athletic greens": "supplement",
    "ag1": "supplement",
}

# Competitor name patterns per category. Matching is case-insensitive
# substring matching against a sponsor's name. Keep these lowercase.
COMPETITOR_PATTERNS = {
    "vpn": [
        "nordvpn",
        "nord vpn",
        "expressvpn",
        "express vpn",
        "surfshark",
        "protonvpn",
        "proton vpn",
        "cyberghost",
        "cyber ghost",
        "pia",
        "private internet access",
        "mullvad",
        "tunnelbear",
        "windscribe",
        "ipvanish",
        "vpn",
    ],
    "website_builder": [
        "squarespace",
        "wix",
        "webflow",
        "godaddy",
        "shopify",
    ],
    "meal_kit": [
        "hellofresh",
        "hello fresh",
        "factor",
        "blue apron",
        "home chef",
        "green chef",
    ],
    "supplement": [
        "athletic greens",
        "ag1",
        "huel",
        "ka'chava",
        "kachava",
    ],
}


def category_for_brand(brand):
    """Return the category for a brand, or None if we don't know it."""
    return BRAND_CATEGORY.get(brand.strip().lower())


def competitor_patterns_for_category(category):
    """Return the list of competitor patterns for a category (may be empty)."""
    return COMPETITOR_PATTERNS.get(category, [])
