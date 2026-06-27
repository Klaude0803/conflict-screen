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


def category_for_sponsor(name):
    """Map a sponsor/brand name to a category, or None if we don't know it.

    Tries an exact brand-map hit first, then case-insensitive substring
    matching against the competitor patterns. Returns None ("unmapped") when
    nothing matches — we never guess a category.
    """
    if not name:
        return None
    lowered = name.strip().lower()

    # Exact brand-map hit (e.g. "NordVPN" -> vpn).
    direct = BRAND_CATEGORY.get(lowered)
    if direct:
        return direct

    # Otherwise look for a competitor pattern contained in the name.
    for category, patterns in COMPETITOR_PATTERNS.items():
        if any(p in lowered for p in patterns):
            return category
    return None


# ===========================================================================
# MARKET RADAR DATA (gambling exclusion, brand lexicon, brief categories).
# All data, no logic. Only ever used to FILTER or LABEL names the API returns
# — never to invent a sponsor.
# ===========================================================================

# Gambling hard-exclusion. Any sponsor whose name matches one of these is
# dropped from market output entirely. Covers sportsbooks, casinos, betting
# apps, odds/tipster brands, bookmakers, real-money fantasy, cash "free to
# play"/prediction apps, sweepstakes-cash apps, and crypto positioned as
# betting. Lowercase substrings, matched case-insensitively.
GAMBLING_PATTERNS = [
    # Sportsbooks / bookmakers
    "bet365", "betway", "betfair", "bet365", "draftkings", "fanduel sportsbook",
    "betmgm", "caesars sportsbook", "pointsbet", "betano", "betclic", "bwin",
    "unibet", "william hill", "ladbrokes", "paddy power", "coral", "skybet",
    "sky bet", "betfred", "888sport", "888 sport", "10bet", "22bet", "1xbet",
    "1x bet", "22 bet", "melbet", "parimatch", "dafabet", "marathonbet",
    "stake.com", "stake.us", "stake casino", "rajabets", "pinnacle sports",
    "sportsbet", "tab ", "tabcorp", "fanduel", "hard rock bet", "fliff",
    "espn bet", "fanatics sportsbook", "betr", "novibet", "superbet",
    # Casinos / slots / sweepstakes-cash
    "casino", "slots", "roulette", "blackjack", "poker", "888casino",
    "luckyland", "chumba", "pulsz", "wow vegas", "high 5 casino", "mcluck",
    "stake.us", "sweepstakes casino", "social casino",
    # Odds / tipsters / bookmakers
    "tipster", "betting tips", "free bets", "free bet", "odds boost",
    "no sweat bet", "parlay pick", "betting picks", "sure bet",
    "sportsbook", "sports book", "sports books", "sportsbooks",
    "bookmaker", "bookmakers", "bookie", "betting site", "betting app",
    # Real-money / cash fantasy & prediction / cash free-to-play
    "prizepicks", "underdog fantasy", "dream11", "my11circle", "mpl ",
    "mobile premier league", "rush fantasy", "sleeper picks", "betr picks",
    "real money", "cash prizes", "win real cash", "play for cash",
    # Crypto positioned as betting
    "crypto casino", "rollbit", "roobet", "duelbits", "bc.game", "betfury",
    "gamdom", "cloudbet", "thunderpick", "betplay",
]

# Borderline names: ambiguous (could be gambling, could be a legitimate app or
# brand of the same name). We do NOT include these in the main table and do NOT
# silently drop them — they go to EXCLUDED FOR REVIEW with this reason.
GAMBLING_BORDERLINE = {
    "sleeper": "Fantasy app; free-to-play vs real-money cash contests unclear.",
    "underdog": "'Underdog' may be Underdog Fantasy (real-money) or an unrelated brand.",
    "stake": "Bare 'Stake' may be the crypto casino or an unrelated brand.",
    "draft": "Bare 'Draft' may be a fantasy/betting product or generic word.",
    "sorare": "Fantasy football NFTs; card trading vs real-money play is unclear.",
    "parlay": "May be a betting parlay product or an unrelated brand.",
    "coinbase": "Crypto exchange; investing vs betting framing depends on the read.",
    "crypto.com": "Crypto exchange; investing vs betting framing depends on the read.",
    "robinhood": "Trading app; investing vs betting framing depends on the read.",
}

# Brand lexicon for the campaign brief categories. Maps a brief category to the
# brand-name patterns that fall in it (lowercase, substring match). Used to (a)
# annotate each surfaced brand with its brief category, (b) decide same-category
# roster conflicts, and (c) recognize known brands inside short-form captions.
BRIEF_CATEGORY_BRANDS = {
    "VPN/privacy": [
        "nordvpn", "expressvpn", "surfshark", "cyberghost", "proton vpn",
        "protonvpn", "private internet access", "pia", "mullvad", "atlas vpn",
        "nordpass", "1password", "dashlane", "incogni", "windscribe", "ipvanish",
    ],
    "sports apparel/footwear": [
        "nike", "adidas", "puma", "under armour", "new balance", "umbro",
        "castore", "hummel", "kappa", "mizuno", "asics", "reebok", "macron",
        "lyle and scott", "represent",
    ],
    "energy/hydration/supplements": [
        "red bull", "redbull", "monster energy", "monster", "prime hydration",
        "prime energy", "gatorade", "powerade", "lucozade", "celsius",
        "ghost energy", "myprotein", "huel", "athletic greens", "ag1",
        "liquid iv", "liquid i.v", "applied nutrition", "grenade",
        "science in sport",
    ],
    "sports/mobile gaming": [
        "ea sports", "ea fc", "ea sports fc", "efootball", "konami",
        "football manager", "top eleven", "dream league soccer", "sofascore",
        "onefootball", "fotmob", "rocket league", "clash of clans", "coin master",
        "raid shadow legends", "monopoly go", "ea play",
    ],
    "streaming": [
        "dazn", "prime video", "amazon prime", "netflix", "disney+", "disney plus",
        "paramount+", "peacock", "fubo", "sling tv", "apple tv", "hulu", "hbo max",
        "tnt sports", "viaplay",
    ],
    "men's grooming/DTC": [
        "manscaped", "dollar shave club", "harry's", "harrys", "gillette",
        "cremo", "every man jack", "hims", "keeps", "beardbrand", "bulldog skincare",
        "estrid",
    ],
    "fan merch/kits/collectibles": [
        "fanatics", "panini", "topps", "kitbag", "classic football shirts",
        "ultimate kit", "footy.com", "footydotcom", "subside sports", "homage",
    ],
    "consumer tech/audio": [
        "samsung", "sony", "bose", "jbl", "anker", "soundcore", "beats by dre",
        "beats", "sennheiser", "logitech", "raycon", "skullcandy", "oneplus",
        "nothing phone", "honor ", "xiaomi", "shokz",
    ],
    "matchday food/snacks/beverages": [
        "doritos", "pepsi", "coca cola", "coca-cola", "coke", "budweiser",
        "bud light", "heineken", "grubhub", "just eat", "deliveroo", "uber eats",
        "domino", "pizza hut", "mcdonald", "pringles", "lays", "lay's", "walkers",
        "monster munch", "red bull",
    ],
    "telecom/mobile": [
        "verizon", "t-mobile", "tmobile", "at&t", "vodafone", "ee ", "o2 ",
        "three mobile", "mint mobile", "visible", "telekom", "orange ",
        "jio", "airtel", "boost mobile",
    ],
}


# Known mega-brands to ALWAYS classify LIKELY AGENCY (enterprise scale, almost
# always agency- or in-house-gated). Editable household names; word-boundary
# matched. This is a heuristic about scale, never a claim about their process.
MEGA_BRANDS = [
    "nike", "adidas", "puma", "under armour", "new balance",
    "samsung", "sony", "lg", "apple", "google", "microsoft", "amazon",
    "coca cola", "coca-cola", "coke", "pepsi", "red bull", "redbull",
    "monster energy", "gatorade", "powerade",
    "ea sports", "ea sports fc", "ea fc", "electronic arts", "konami",
    "netflix", "disney", "hbo max", "prime video", "spotify", "youtube",
    "mcdonald", "burger king", "budweiser", "bud light", "heineken",
    "verizon", "at&t", "t-mobile", "vodafone", "visa", "mastercard", "paypal",
    "intel", "amd", "nvidia", "meta", "bose", "jbl", "beats by dre",
    "xbox", "playstation", "nintendo", "doritos", "pringles", "gillette",
    "l'oreal", "loreal", "dazn",
]


def is_gambling(name):
    """True if a sponsor name matches the gambling hard-exclusion list."""
    if not name:
        return False
    lowered = " " + name.strip().lower() + " "
    return any(p in lowered or p in name.strip().lower() for p in GAMBLING_PATTERNS)


def is_mega_brand(name):
    """True if a brand is on the editable mega-brand (LIKELY AGENCY) list."""
    if not name:
        return False
    lowered = name.strip().lower()
    return any(_pattern_matches(p, lowered) for p in MEGA_BRANDS)


def gambling_borderline_reason(name):
    """Return a reason string if a name is a borderline gambling case, else None.

    Matches on whole-word-ish boundaries so 'stake' flags 'Stake' but not
    'beefsteak'. Only borderline standalone names are caught here.
    """
    if not name:
        return None
    tokens = set(
        "".join(c if c.isalnum() else " " for c in name.lower()).split()
    )
    for pattern, reason in GAMBLING_BORDERLINE.items():
        # Borderline keys are single words; match as a standalone token.
        if pattern in tokens:
            return reason
    return None


import re as _re


def _pattern_matches(pattern, text):
    """Word-boundary match so short patterns ('ee', 'o2', 'max') only fire on
    a standalone token, never inside another word ('free', 'maximum')."""
    pattern = pattern.strip()
    if not pattern:
        return False
    return _re.search(r"(?<!\w)" + _re.escape(pattern) + r"(?!\w)", text) is not None


def brief_category_for(name):
    """Map a brand name to one brief category, or 'uncategorized (brief)'."""
    if not name:
        return "uncategorized (brief)"
    lowered = name.strip().lower()
    for category, patterns in BRIEF_CATEGORY_BRANDS.items():
        if any(_pattern_matches(p, lowered) for p in patterns):
            return category
    return "uncategorized (brief)"


def known_brands_in_text(text):
    """Return the brief-lexicon brand display patterns found in a caption.

    Used for conservative short-form extraction: we only name a brand inside a
    paid-partnership post when a known brand pattern actually appears as a
    standalone token (word-boundary matched). Returns (pattern, brief_category).
    """
    if not text:
        return []
    lowered = text.lower()
    hits = []
    for category, patterns in BRIEF_CATEGORY_BRANDS.items():
        for p in patterns:
            if _pattern_matches(p, lowered):
                hits.append((p.strip(), category))
    return hits
