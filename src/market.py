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


# Common suffixes a channel tacks onto its own name; stripped before matching
# so "Tom Spark's Reviews" still matches a "Tomspark" self-mention.
_SELF_REF_SUFFIXES = ("reviews", "review", "official", "channel", "tube", "tv", "yt", "hd")
_MIN_TOKEN_LEN = 4  # guard against tiny fragments causing false matches


def _strip_self_ref_suffix(norm):
    for suffix in _SELF_REF_SUFFIXES:
        if norm.endswith(suffix) and len(norm) - len(suffix) >= _MIN_TOKEN_LEN:
            return norm[: -len(suffix)]
    return norm


def _channel_tokens(record):
    """Normalized identifiers for a creator's own channel name and handle."""
    tokens = set()
    for raw in (record.get("name"), record.get("handle")):
        if not raw:
            continue
        norm = _norm_key(raw)
        if len(norm) >= _MIN_TOKEN_LEN:
            tokens.add(norm)
            stripped = _strip_self_ref_suffix(norm)
            if len(stripped) >= _MIN_TOKEN_LEN:
                tokens.add(stripped)
    return tokens


def _is_self_reference(sponsor_name, channel_tokens):
    """True when a sponsor name is essentially the creator's own channel.

    Matches case-insensitively, ignoring spaces/punctuation and common
    suffixes, when the sponsor equals, contains, or is contained by a channel
    token (the creator self-referencing, not a real brand).
    """
    if not channel_tokens:
        return False
    candidates = {_norm_key(sponsor_name)}
    candidates.add(_strip_self_ref_suffix(next(iter(candidates))))
    for token in channel_tokens:
        for cand in candidates:
            if not cand:
                continue
            if cand == token:
                return True
            if len(token) >= _MIN_TOKEN_LEN and token in cand:
                return True
            if len(cand) >= _MIN_TOKEN_LEN and cand in token:
                return True
    return False


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
    dropped_self = 0

    for record in records:
        handle = record.get("handle")
        channel_tokens = _channel_tokens(record)
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
            # Drop the creator self-referencing its own channel name/handle.
            if _is_self_reference(name, channel_tokens):
                dropped_self += 1
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
        "self_reference": dropped_self,
        "total": dropped_low + dropped_generic + dropped_self,
        "min_confidence": (min_confidence or "medium").lower(),
    }
    return rows, stats


# ===========================================================================
# MARKET RADAR: the football brief — gambling exclusion, live/evergreen tag,
# roster conflict + fit, brief-category annotation, and multi-platform.
# Reuses the filters above (_within_window, _confidence_rank, _is_generic,
# _is_self_reference, _norm_key). Still: only ever filters/labels what the API
# returned; never invents a sponsor.
# ===========================================================================
LIVE_DAYS = 30  # most-recent placement within 30 days -> LIVE (running now)

# Rules-based fit: which roster content-niche tag words a brief category speaks
# to. A creator "fits" a brand when its tag words intersect this set. This is a
# deterministic suggestion from the supplied tags, never an invented opinion.
BRIEF_CATEGORY_FIT_TAGS = {
    # Specialist categories omit the universal football/soccer tags so they
    # pick out the genuinely-relevant creators (e.g. gaming -> Fiago); broad
    # consumer categories keep them since they fit the football audience.
    "VPN/privacy": {"tech", "gaming", "esports", "streaming", "dual",
                    "platform", "privacy"},
    "sports apparel/footwear": {"football", "soccer", "highlights", "commentary",
                                "skills", "comedy", "entertainment", "tactics"},
    "energy/hydration/supplements": {"fitness", "skills", "gaming", "esports",
                                     "highlights"},
    "sports/mobile gaming": {"gaming", "fifa", "esports"},
    "streaming": {"football", "soccer", "highlights", "commentary", "analysis",
                  "live", "event", "entertainment", "watchalong"},
    "men's grooming/DTC": {"football", "soccer", "comedy", "entertainment",
                           "lifestyle", "opinion", "debate"},
    "fan merch/kits/collectibles": {"football", "soccer", "kits", "collectibles",
                                    "fan", "comedy", "entertainment", "opinion", "debate"},
    "consumer tech/audio": {"tech", "gaming", "esports", "dual",
                            "platform", "tiktok", "audio"},
    "matchday food/snacks/beverages": {"live", "event", "ground", "entertainment",
                                       "comedy", "watchalong"},
    "telecom/mobile": {"football", "soccer", "tiktok", "dual", "platform",
                       "highlights", "commentary"},
}


# Reachability heuristic thresholds (creator mix + brand size). A suggestion
# from real signal, never a claim about a brand's actual process.
_LARGE_SUBS = 1_000_000     # a creator at/above this counts as "large"
_DIRECT_MAX_CREATORS = 4    # "a few" distinct creators
_AGENCY_MIN_CREATORS = 6    # "very high" distinct-creator count
_AGENCY_MIN_LARGE = 2       # "several" large creators

_CONTACT_DIRECT = (
    "Check by hand: company website + partnerships/press page; founder or "
    "growth/partnerships lead on LinkedIn; a partnerships@ or hello@ address. "
    "Verify before any outreach."
)
_CONTACT_AGENCY = (
    "Likely agency or in-house enterprise team; expect gatekeeping. No direct "
    "cold surface suggested."
)
_CONTACT_UNCLEAR = (
    "Mixed signals; check the website and LinkedIn to confirm who owns "
    "partnerships before reaching out."
)

# Sort priority so LIKELY DIRECT floats to the top.
_REACH_RANK = {"LIKELY DIRECT": 0, "UNCLEAR": 1, "LIKELY AGENCY": 2}


def _reachability(display, distinct_creators, creator_subs):
    """Classify a brand's reachability tier from real signal only.

    creator_subs: list of subscriber counts (None for unknown) of contributing
    creators. Returns (tier, contact_starting_point). Heuristic, not a claim
    about the brand's real process.
    """
    if config.is_mega_brand(display):
        return "LIKELY AGENCY", _CONTACT_AGENCY

    known = [s for s in creator_subs if isinstance(s, int)]
    large = sum(1 for s in known if s >= _LARGE_SUBS)

    # Enterprise scale: several large creators, or a very wide creator spread.
    if large >= _AGENCY_MIN_LARGE or distinct_creators >= _AGENCY_MIN_CREATORS:
        return "LIKELY AGENCY", _CONTACT_AGENCY

    # Concentrated on a few mid-sized creators, none confirmed large.
    if distinct_creators <= _DIRECT_MAX_CREATORS and large == 0 and known:
        return "LIKELY DIRECT", _CONTACT_DIRECT

    return "UNCLEAR", _CONTACT_UNCLEAR


def _recency_tag(date_str):
    """LIVE (<30d), ACTIVE (<=6mo), or None (older -> dropped)."""
    if not date_str:
        return None
    try:
        when = datetime.strptime(date_str, "%Y-%m-%d")
    except (ValueError, TypeError):
        return None
    age = datetime.utcnow() - when
    if age <= timedelta(days=LIVE_DAYS):
        return "LIVE (running now)"
    if age <= timedelta(days=30 * 6):
        return "ACTIVE"
    return None


def _fmt_month(date_str):
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").strftime("%b %Y")
    except (ValueError, TypeError):
        return date_str or ""


def _tag_words(tags):
    """Flatten a list of niche-tag strings into a set of lowercase words."""
    words = set()
    for t in tags or []:
        for w in "".join(c if c.isalnum() else " " for c in t.lower()).split():
            words.add(w)
    return words


def _roster_map(roster):
    """Normalize a roster dict {handle: [tags]} -> {handle_lower: set(words)}."""
    out = {}
    for handle, tags in (roster or {}).items():
        out[handle.lower().lstrip("@")] = _tag_words(tags)
    return out


def aggregate_radar(records, *, scan_months, conflict_months, roster=None,
                    min_confidence="medium"):
    """Aggregate multi-platform sponsor records into the ranked brand radar.

    Returns (rows, excluded_for_review, stats). Each row has brand, brief
    category, platforms, proof, recency tag, suggested fit, roster conflict,
    most recent date, verification, distinct creators, total placements.
    Brands older than 6 months (no LIVE/ACTIVE tag) are dropped from the run.
    """
    min_rank = _CONFIDENCE_RANK.get((min_confidence or "medium").lower(), 2)
    roster_words = _roster_map(roster)

    # 1. Roster sponsorship history within the conflict window (12mo), per
    #    roster creator, used for the roster-conflict flag. Confirmed = the
    #    creator's record was real (verified) and didn't error.
    roster_history = {h: set() for h in roster_words}   # handle -> {brief_cat}
    roster_brands = {h: set() for h in roster_words}     # handle -> {brand key}
    roster_confirmed = set()
    for rec in records:
        h = (rec.get("handle") or "").lower().lstrip("@")
        if h not in roster_words:
            continue
        if rec.get("verified") and not rec.get("error"):
            roster_confirmed.add(h)
        for s in rec.get("recent_sponsors") or []:
            name = (s.get("name") or "").strip()
            if not name or config.is_gambling(name):
                continue
            if not _within_window(s.get("date"), conflict_months):
                continue
            roster_history[h].add(config.brief_category_for(name))
            roster_brands[h].add(_norm_key(name))

    # 2. Aggregate sponsors across all records (within the scan window).
    brands = {}
    dropped = {"low_confidence": 0, "generic": 0, "self_reference": 0,
               "gambling": 0}
    excluded_for_review = {}  # brand display -> reason

    for rec in records:
        handle = rec.get("handle")
        channel_tokens = _channel_tokens(rec)
        verified = bool(rec.get("verified")) and not rec.get("error")
        for s in rec.get("recent_sponsors") or []:
            name = (s.get("name") or "").strip()
            if not name:
                continue
            if not _within_window(s.get("date"), scan_months):
                continue
            # Gambling hard-exclusion: drop entirely.
            if config.is_gambling(name):
                dropped["gambling"] += 1
                continue
            # Borderline gambling: never in the main table; list for review.
            reason = config.gambling_borderline_reason(name)
            if reason:
                excluded_for_review.setdefault(name, reason)
                continue
            if _is_generic(name):
                dropped["generic"] += 1
                continue
            if _is_self_reference(name, channel_tokens):
                dropped["self_reference"] += 1
                continue
            if _confidence_rank(s.get("confidence")) < min_rank:
                dropped["low_confidence"] += 1
                continue

            key = _norm_key(name)
            if not key:
                continue
            e = brands.get(key)
            if e is None:
                e = {"names": {}, "creators": set(), "placements": 0,
                     "platforms": set(), "most_recent": None,
                     "examples": [], "verified_any": False, "creator_subs": {}}
                brands[key] = e
            e["names"][name] = e["names"].get(name, 0) + 1
            e["placements"] += 1
            platform = s.get("platform") or rec.get("platform") or "YouTube"
            e["platforms"].add(platform)
            if verified:
                e["verified_any"] = True
            date = s.get("date")
            if handle:
                e["creators"].add(handle)
                # Largest known size seen for this creator (subs/followers).
                subs = rec.get("subscribers")
                if isinstance(subs, int):
                    prev = e["creator_subs"].get(handle)
                    e["creator_subs"][handle] = max(prev or 0, subs)
                if len(e["examples"]) < 3 and handle not in [x[0] for x in e["examples"]]:
                    e["examples"].append((handle, date, platform))
            if date and (e["most_recent"] is None or date > e["most_recent"]):
                e["most_recent"] = date

    # 3. Build rows: brief category, recency tag (drop > 6mo), conflict, fit.
    rows = []
    for e in brands.values():
        display = max(e["names"].items(), key=lambda kv: kv[1])[0]
        brief_cat = config.brief_category_for(display)
        tag = _recency_tag(e["most_recent"])
        if tag is None:
            continue  # older than 6 months -> dropped from this run

        # Roster conflict: a roster creator already ran this brand or its
        # brief category within the conflict window.
        brand_key = _norm_key(display)
        conflicted = [h for h in roster_words
                      if brand_key in roster_brands.get(h, set())
                      or brief_cat in roster_history.get(h, set())]
        if conflicted:
            conflict = "CONFLICT (" + ", ".join(sorted(conflicted)) + ")"
        elif roster_words and roster_confirmed >= set(roster_words):
            conflict = "CLEAR"
        elif not roster_words:
            conflict = "n/a (no roster)"
        else:
            conflict = "UNVERIFIED"

        # Suggested fit: roster creators whose tag words intersect the brief
        # category's fit tags. Rules-based from the supplied tags.
        fit_tags = BRIEF_CATEGORY_FIT_TAGS.get(brief_cat, set())
        fit = [h for h, words in roster_words.items() if words & fit_tags]

        proof = "; ".join(
            f"{h} on {pf} ({_fmt_month(d)})" for h, d, pf in e["examples"]
        )
        # Reachability tier from creator mix + brand size (real signal only).
        reach, contact = _reachability(
            display, len(e["creators"]), list(e["creator_subs"].values())
        )
        rows.append({
            "brand": display,
            "brief_category": brief_cat,
            "platforms": ", ".join(sorted(e["platforms"])),
            "proof": proof,
            "recency_tag": tag,
            "reachability": reach,
            "contact_start": contact,
            "suggested_fit": ", ".join(sorted(fit)) if fit else "none",
            "roster_conflict": conflict,
            "most_recent_date": e["most_recent"] or "",
            "verification": "verified" if e["verified_any"] else "sample/unverified",
            "distinct_creators": len(e["creators"]),
            "total_placements": e["placements"],
        })

    # Sort by reachability (LIKELY DIRECT first), then by activity.
    rows.sort(key=lambda r: (
        _REACH_RANK.get(r["reachability"], 1),
        -r["distinct_creators"], -r["total_placements"],
    ))
    stats = dict(dropped)
    stats["min_confidence"] = (min_confidence or "medium").lower()
    stats["excluded_for_review"] = len(excluded_for_review)
    review_list = [{"brand": b, "reason": r} for b, r in sorted(excluded_for_review.items())]
    return rows, review_list, stats
