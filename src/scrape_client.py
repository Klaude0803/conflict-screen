"""Client for fetching creator data.

By default this runs in MOCK mode and returns clearly-labeled sample data
so the tool works with no API key. When you are ready to use the real
Scrape Creators API, fill in the single marked section in
``_fetch_live`` and run with ``--live``.

Guiding rule: we never invent missing data. If a field is unknown it stays
empty (None / empty list), and every record carries a ``verified`` flag so
downstream code can tell confirmed data from mock or partial data.
"""

import os
import time
from datetime import datetime, timedelta

import config

# Live Scrape Creators API settings.
BASE_URL = "https://api.scrapecreators.com"
API_KEY_ENV = "SCRAPECREATORS_API_KEY"

# Safety caps so a single creator can never trigger unbounded API spend.
_MAX_VIDEO_PAGES = 5        # pages of channel uploads to scan, newest first
_MAX_SPONSOR_LOOKUPS = 40   # in-window videos to query for sponsors
_MAX_SEARCH_PAGES = 5       # pages of channel search results to scan

# Retry policy for transient upstream errors (5xx / 429).
_MAX_RETRIES = 3            # extra attempts after the first
_RETRY_BACKOFF = 1.0        # seconds; doubled each retry (1s, 2s, 4s)


class _CreatorLookupError(Exception):
    """A recoverable, per-creator failure — the batch should continue."""


def _empty_record(handle):
    """A record skeleton with everything blank and verified=False.

    This is the shape every record follows. Missing fields stay empty
    rather than being guessed at.
    """
    return {
        "handle": handle,
        "name": None,
        "platform": None,
        "subscribers": None,
        # audience_geo maps ISO country code -> percent of audience (0-100).
        "audience_geo": {},
        # recent_sponsors is a list of {"name", "category", "date"} dicts.
        "recent_sponsors": [],
        # verified is True only when the data is confirmed real (live API).
        "verified": False,
        # source labels where the data came from, for transparency.
        "source": None,
        # error holds a short reason when a live lookup failed for this
        # creator; it stays None for mock data and successful live lookups.
        "error": None,
        # channel_country is the channel's OWN stated country (from its
        # profile) — NOT audience location. Stays None unless the API
        # returns it. audience_geo above is always left empty for YouTube.
        "channel_country": None,
        # Computed public-signal metrics. None = NOT FOUND (never estimated).
        "recent_avg_views": None,        # mean of recent uploads' view counts
        "view_consistency": None,        # {"label", "cov", "n"} spread signal
        "engagement": None,              # short-form engagement dict (IG)
    }


# ---------------------------------------------------------------------------
# MOCK data. Clearly labeled sample creators. Dates are generated relative to
# "now" so some sponsorships fall inside the 12-month window and some don't.
# A couple of records intentionally leave fields empty to exercise the
# "never invent missing data" / UNVERIFIED paths.
# ---------------------------------------------------------------------------
def _months_ago(months):
    return (datetime.utcnow() - timedelta(days=30 * months)).strftime("%Y-%m-%d")


_MOCK_CREATORS = {
    "techreviewerjane": {
        "name": "Jane Tech (SAMPLE)",
        "platform": "YouTube",
        "subscribers": 1250000,
        "audience_geo": {"US": 48, "GB": 12, "CA": 9, "AU": 6, "DE": 8, "IN": 17},
        "recent_sponsors": [
            {"name": "NordVPN", "category": "vpn", "months_ago": 3, "confidence": "high"},
            {"name": "Squarespace", "category": "website_builder", "months_ago": 7, "confidence": "medium"},
        ],
    },
    "gadgetguygreg": {
        "name": "Gadget Greg (SAMPLE)",
        "platform": "YouTube",
        "subscribers": 540000,
        "audience_geo": {"US": 22, "IN": 31, "BR": 18, "GB": 6, "CA": 3, "PH": 20},
        "recent_sponsors": [
            {"name": "Squarespace", "category": "website_builder", "months_ago": 2, "confidence": "high"},
            {"name": "Honey", "category": "shopping", "months_ago": 5, "confidence": "low"},
        ],
    },
    "privacypaula": {
        "name": "Privacy Paula (SAMPLE)",
        "platform": "YouTube",
        "subscribers": 320000,
        "audience_geo": {"US": 55, "CA": 14, "GB": 11, "AU": 8, "DE": 12},
        "recent_sponsors": [
            # An old VPN deal, just outside the 12-month window.
            {"name": "ExpressVPN", "category": "vpn", "months_ago": 15, "confidence": "high"},
        ],
    },
    "lifestyleliam": {
        "name": "Lifestyle Liam (SAMPLE)",
        "platform": "Instagram",
        "subscribers": 89000,
        "audience_geo": {"US": 30, "GB": 9, "CA": 5, "AU": 4, "FR": 22, "ES": 30},
        "recent_sponsors": [
            {"name": "HelloFresh", "category": "meal_kit", "months_ago": 4, "confidence": "medium"},
        ],
    },
    "newcreatornina": {
        # Brand new creator: we have her handle and platform but NO confirmed
        # sponsorship history. Fields we don't know stay empty -> UNVERIFIED.
        "name": "Newcomer Nina (SAMPLE)",
        "platform": "TikTok",
        "subscribers": None,
        "audience_geo": {},
        "recent_sponsors": [],
    },
    # VPN-niche sample creators (handles match the source-mode mock channels)
    # so market mode's --query path produces a meaningful brand map in mock.
    "vpnvinny": {
        "name": "VPN Vinny (SAMPLE)",
        "platform": "YouTube",
        "subscribers": 845000,
        "audience_geo": {},
        "recent_sponsors": [
            {"name": "NordVPN", "category": "vpn", "months_ago": 1, "confidence": "high"},
            {"name": "Surfshark", "category": "vpn", "months_ago": 4, "confidence": "medium"},
            {"name": "Squarespace", "category": "website_builder", "months_ago": 8, "confidence": "high"},
            # A generic, non-brand phrase the API sometimes emits -> dropped.
            {"name": "any VPN provider", "category": "vpn", "months_ago": 1, "confidence": "medium"},
        ],
    },
    "securitysam": {
        "name": "Security Sam (SAMPLE)",
        "platform": "YouTube",
        "subscribers": 11500,
        "audience_geo": {},
        "recent_sponsors": [
            {"name": "NordVPN", "category": "vpn", "months_ago": 2, "confidence": "high"},
            {"name": "ExpressVPN", "category": "vpn", "months_ago": 6, "confidence": "medium"},
        ],
    },
    "streamguru": {
        "name": "Stream Guru (SAMPLE)",
        "platform": "YouTube",
        "subscribers": 2400000,
        "audience_geo": {},
        "recent_sponsors": [
            {"name": "Surfshark", "category": "vpn", "months_ago": 3, "confidence": "high"},
            {"name": "Squarespace", "category": "website_builder", "months_ago": 5, "confidence": "medium"},
            # The creator self-referencing its own channel -> dropped.
            {"name": "Stream Guru", "category": None, "months_ago": 2, "confidence": "high"},
        ],
    },
    "tinytechtom": {
        "name": "Tiny Tech Tom (SAMPLE)",
        "platform": "YouTube",
        "subscribers": 4200,
        "audience_geo": {},
        "recent_sponsors": [
            {"name": "NordVPN", "category": "vpn", "months_ago": 2, "confidence": "high"},
            # Low-confidence guess -> dropped at the default medium threshold.
            {"name": "Notion", "category": None, "months_ago": 3, "confidence": "low"},
        ],
    },
}


def _fetch_mock(handle, months=None):
    record = _empty_record(handle)
    record["source"] = "MOCK (sample data — not real)"
    data = _MOCK_CREATORS.get(handle.strip().lower().lstrip("@"))
    if data is None:
        # Unknown handle in mock mode: we don't make anything up. We return
        # the empty skeleton so downstream treats it as UNVERIFIED.
        return record

    record["name"] = data.get("name")
    record["platform"] = data.get("platform")
    record["subscribers"] = data.get("subscribers")
    record["audience_geo"] = dict(data.get("audience_geo") or {})
    sponsors = []
    for s in data.get("recent_sponsors") or []:
        # When a lookback is given (market mode), drop out-of-window sponsors
        # so mock mirrors live (which only returns in-window placements).
        if months is not None and s["months_ago"] > months:
            continue
        sponsors.append({
            "name": s["name"],
            "category": s.get("category"),
            "date": _months_ago(s["months_ago"]),
            "confidence": s.get("confidence"),
        })
    record["recent_sponsors"] = sponsors
    # Sample view metrics derived from subs (clearly mock, never live).
    _mock_view_metrics(record)
    # Mock data is sample data, so it is NOT verified.
    record["verified"] = False
    return record


def _mock_view_metrics(record):
    """Synthesize sample recent-views/consistency for MOCK records only."""
    subs = record.get("subscribers")
    if isinstance(subs, int) and subs > 0:
        sample = [int(subs * f) for f in (0.32, 0.28, 0.35, 0.22, 0.30)]
        _apply_view_metrics(record, sample)


# ---------------------------------------------------------------------------
# MOCK data for SOURCE mode. Clearly-labeled sample channels returned by a
# fake "search". These carry a stated channel country (not audience location)
# and varied subscriber counts so the size filters can be demonstrated. They
# have NO sponsor history — exactly like the lightweight live source fetch —
# so the existing conflict screen reports them UNVERIFIED until you run full
# screen mode on the shortlist.
# ---------------------------------------------------------------------------
_MOCK_CHANNELS = {
    "vpnvinny": {"name": "VPN Vinny (SAMPLE)", "subscribers": 845000, "country": "United States"},
    "privacypaula": {"name": "Privacy Paula (SAMPLE)", "subscribers": 320000, "country": "United Kingdom"},
    "securitysam": {"name": "Security Sam (SAMPLE)", "subscribers": 11500, "country": "Canada"},
    "streamguru": {"name": "Stream Guru (SAMPLE)", "subscribers": 2400000, "country": "Australia"},
    "tinytechtom": {"name": "Tiny Tech Tom (SAMPLE)", "subscribers": 4200, "country": "United States"},
    # No country/subs returned for this one -> stays empty, never invented.
    "mysterymaya": {"name": "Mystery Maya (SAMPLE)", "subscribers": None, "country": None},
}

# The fake search returns these handles (in rank order) for any query.
_MOCK_SEARCH_ORDER = [
    "vpnvinny", "privacypaula", "securitysam",
    "streamguru", "tinytechtom", "mysterymaya",
]


def _fetch_channel_mock(handle):
    """Lightweight mock channel-details fetch for source mode (no sponsors)."""
    record = _empty_record(handle)
    record["source"] = "MOCK (sample data — not real)"
    data = _MOCK_CHANNELS.get(handle.strip().lower().lstrip("@"))
    if data is None:
        # Unknown handle: invent nothing, leave the skeleton -> UNVERIFIED.
        return record
    record["platform"] = "YouTube"
    record["name"] = data.get("name")
    record["subscribers"] = data.get("subscribers")
    record["channel_country"] = data.get("country")
    # No sponsor pull in source mode, and never any audience_geo.
    record["verified"] = False  # sample data is not verified
    return record


def _search_channels_mock(query, limit):
    """Fake channel search: returns clearly-labeled sample candidates."""
    candidates = []
    for handle in _MOCK_SEARCH_ORDER[:limit]:
        data = _MOCK_CHANNELS[handle]
        candidates.append({
            "handle": handle,
            "channel_id": f"MOCK_{handle}",
            "name": data.get("name"),
            "subs_hint": data.get("subscribers"),
        })
    return candidates


def _apply_view_metrics(record, view_counts):
    """Set recent_avg_views + view_consistency from real public view counts.

    Uses the most recent 10 samples. Leaves both None (NOT FOUND) if the API
    returned no view counts. Never estimates a number.
    """
    sample = [v for v in view_counts if isinstance(v, int) and v >= 0][:10]
    if not sample:
        return
    mean = sum(sample) / len(sample)
    record["recent_avg_views"] = int(round(mean))
    if len(sample) >= 2 and mean > 0:
        var = sum((v - mean) ** 2 for v in sample) / len(sample)
        cov = (var ** 0.5) / mean  # coefficient of variation
        label = "steady" if cov < 0.5 else "variable" if cov < 1.0 else "erratic"
        record["view_consistency"] = {"label": label, "cov": round(cov, 2),
                                      "n": len(sample)}
    else:
        record["view_consistency"] = {"label": "n/a (one sample)", "cov": None,
                                      "n": len(sample)}


def _apply_ig_engagement(record, posts_stats):
    """Set engagement from IG post like/comment/play counts (raw signal, not a
    rate). posts_stats is a list of (likes, comments, plays). NOT FOUND if empty."""
    likes = [p[0] for p in posts_stats if isinstance(p[0], int)]
    comments = [p[1] for p in posts_stats if isinstance(p[1], int)]
    if not likes and not comments:
        return
    n = max(len(likes), len(comments)) or 1
    record["engagement"] = {
        "avg_likes": int(round(sum(likes) / len(likes))) if likes else None,
        "avg_comments": int(round(sum(comments) / len(comments))) if comments else None,
        "posts": n,
        "note": "raw per-post engagement (not a follower-normalized rate)",
    }


def _parse_iso_dt(value):
    """Parse an ISO-8601 timestamp (e.g. '2025-01-23T22:48:53.914Z') to a
    naive UTC datetime, or None if it can't be parsed."""
    if not value:
        return None
    text = value.replace("Z", "+0000")
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%S%z"):
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=None)
        except ValueError:
            continue
    return None


def _live_error_record(handle, reason):
    """Build a record for a creator whose live lookup failed.

    Nothing is invented: fields stay empty, verified stays False, and the
    short reason is attached so the screener reports UNVERIFIED with context.
    """
    record = _empty_record(handle)
    record["source"] = "Scrape Creators API (live)"
    record["verified"] = False
    record["error"] = reason
    return record


# ===========================================================================
# LIVE SCRAPE CREATORS API INTEGRATION (the marked spot).
#
# Shared infrastructure used by BOTH screen mode and source mode:
#   - _require_api_key(): reads x-api-key value from SCRAPECREATORS_API_KEY
#   - _api_get():         one GET with retry/backoff + terminal-error mapping
#   - _safe_live_fetch(): wraps a per-creator fetch so one failure marks just
#                         that creator UNVERIFIED and the batch continues
#
# Endpoints:
#   GET /v1/youtube/channel        -> name + subscriberCount + country + id
#   GET /v1/youtube/channel-videos -> recent uploads with publish dates
#   GET /v1/youtube/video/sponsors -> brand names for each in-window upload
#   GET /v1/youtube/search         -> channel candidates for a topic query
#
# We set verified=True only when a lookup actually returns data, map only
# fields the API returns (missing ones stay empty), and deliberately do NOT
# populate audience_geo — Scrape Creators does not expose YouTube
# audience-location data, so geo reads UNKNOWN rather than us inventing it.
# channel_country below is the channel's OWN stated country, not audience.
# ===========================================================================
def _require_api_key():
    """Return the API key, or raise a clear error if it isn't configured."""
    api_key = os.environ.get(API_KEY_ENV)
    if not api_key:
        # A totally missing key is a configuration problem, not a per-creator
        # one, so fail fast instead of producing identical per-row errors.
        raise RuntimeError(
            f"Live mode requested but {API_KEY_ENV} is not set. Export your "
            "Scrape Creators API key, or run without --live to use mock data."
        )
    return api_key


def _api_get(path, params, api_key):
    """One GET against the API with retry/backoff for transient failures.

    Transient upstream errors (5xx) and rate limits (429) get a few quick
    retries; auth (401), payment (402) and not-found (404) are terminal and
    raise ``_CreatorLookupError``.
    """
    import requests  # imported lazily so mock mode never needs requests

    last_resp = None
    for attempt in range(_MAX_RETRIES + 1):
        resp = requests.get(
            BASE_URL + path,
            params=params,
            headers={"x-api-key": api_key},
            timeout=30,
        )
        if resp.status_code == 401:
            raise _CreatorLookupError(f"API auth failed (401) — check {API_KEY_ENV}.")
        if resp.status_code == 402:
            raise _CreatorLookupError(
                "API payment required (402) — account out of credits."
            )
        if resp.status_code == 404:
            raise _CreatorLookupError("Channel/video not found (404).")
        if resp.status_code == 429 or resp.status_code >= 500:
            last_resp = resp
            if attempt < _MAX_RETRIES:
                time.sleep(_RETRY_BACKOFF * (2 ** attempt))
                continue
        resp.raise_for_status()
        return resp.json()
    # Exhausted retries on a transient error.
    last_resp.raise_for_status()


def _safe_live_fetch(handle, fetch_fn):
    """Run a per-creator live fetch, converting any failure into an
    UNVERIFIED record so one bad lookup never kills the batch."""
    import requests
    try:
        return fetch_fn()
    except _CreatorLookupError as e:
        return _live_error_record(handle, str(e))
    except requests.RequestException as e:
        return _live_error_record(handle, f"Network/API error: {e}")
    except Exception as e:  # noqa: BLE001 - never let one creator kill the batch
        return _live_error_record(handle, f"Unexpected error: {e}")


def _map_channel_basic(handle, channel):
    """Map a /v1/youtube/channel response into a verified record skeleton.

    Only fills fields the API actually returned. Leaves recent_sponsors and
    audience_geo empty; the caller adds sponsors for full screen mode.
    """
    record = _empty_record(handle)
    record["source"] = "Scrape Creators API (live)"
    record["verified"] = True  # the channel lookup returned real data
    record["platform"] = "YouTube"
    if channel.get("name"):
        record["name"] = channel["name"]
    if channel.get("subscriberCount") is not None:
        record["subscribers"] = channel["subscriberCount"]
    if channel.get("country"):
        # The channel's OWN stated country — not audience location.
        record["channel_country"] = channel["country"]
    return record


def _fetch_live(handle, months=None, max_videos=None):
    """Full fetch: channel -> recent uploads -> sponsors.

    ``months`` overrides the lookback window (defaults to config value).
    ``max_videos`` caps how many in-window uploads we pull sponsors for
    (defaults to _MAX_SPONSOR_LOOKUPS). Both let market mode bound spend.
    """
    api_key = _require_api_key()
    clean_handle = handle.strip().lstrip("@")
    months = config.LOOKBACK_MONTHS if months is None else months
    max_videos = _MAX_SPONSOR_LOOKUPS if max_videos is None else max_videos

    def _inner():
        # --- 1. Channel details -------------------------------------------
        channel = _api_get("/v1/youtube/channel", {"handle": clean_handle}, api_key)
        record = _map_channel_basic(handle, channel)
        channel_id = channel.get("channelId")

        # --- 2. Recent uploads inside the lookback window -----------------
        cutoff = datetime.utcnow() - timedelta(days=30 * months)
        in_window = []  # list of {"url", "date"} for videos within the window
        recent_views = []  # view counts of recent in-window uploads (real only)
        token = None
        for _ in range(_MAX_VIDEO_PAGES):
            params = {"channelId": channel_id} if channel_id else {"handle": clean_handle}
            if token:
                params["continuationToken"] = token

            page = _api_get("/v1/youtube/channel-videos", params, api_key)
            videos = page.get("videos") or []
            reached_old = False
            for v in videos:
                published = _parse_iso_dt(v.get("publishedTime"))
                if published is None:
                    continue
                # Uploads come newest-first, so once we pass the cutoff we can
                # stop paging.
                if published < cutoff:
                    reached_old = True
                    break
                vc = v.get("viewCountInt")
                if isinstance(vc, int) and vc >= 0:
                    recent_views.append(vc)
                if v.get("url"):
                    in_window.append({
                        "url": v["url"],
                        "date": published.strftime("%Y-%m-%d"),
                    })

            token = page.get("continuationToken")
            # Stop paging once we already have enough in-window uploads to
            # cover the sponsor cap — no point fetching more pages.
            if reached_old or len(in_window) >= max_videos or not token or not videos:
                break

        # Recent average views + view consistency from the last 5-10 uploads'
        # PUBLIC view counts. NOT FOUND if the API returned no view counts.
        _apply_view_metrics(record, recent_views)

        # --- 3. Sponsors for each in-window upload ------------------------
        sponsors = []
        for vid in in_window[:max_videos]:
            data = _api_get("/v1/youtube/video/sponsors", {"url": vid["url"]}, api_key)
            for s in data.get("suspectedSponsors") or []:
                name = s.get("name")
                if not name:
                    continue
                sponsors.append({
                    "name": name,
                    # The API doesn't categorize sponsors; conflict screening
                    # matches by name pattern, so we leave category empty.
                    "category": None,
                    "date": vid["date"],
                    # Confidence as returned by the API (high/medium/low);
                    # used by market mode's filter. Never relabeled.
                    "confidence": s.get("confidence"),
                })
        record["recent_sponsors"] = sponsors
        return record

    return _safe_live_fetch(handle, _inner)


# A subscriber count of 0 / null / missing on the channel endpoint is usually a
# transient miss, so we re-fetch the channel a couple of times before accepting
# the count as genuinely unavailable. We never invent or estimate a number.
_SUBS_RETRIES = 2


def _positive_int(value):
    """Return value if it's a positive int, else None (0/None/missing -> None)."""
    return value if isinstance(value, int) and value > 0 else None


def _fetch_channel_live(handle):
    """Lightweight source-mode fetch: channel details + country only.

    Exactly one lookup per candidate in the happy path. If the subscriber count
    comes back 0/empty/missing, the channel call is retried once or twice with
    backoff (transient misses are common) before the count is accepted as
    genuinely unavailable. Sponsor history is NOT pulled here.
    """
    api_key = _require_api_key()
    clean_handle = handle.strip().lstrip("@")

    def _inner():
        channel = None
        for attempt in range(_SUBS_RETRIES + 1):
            channel = _api_get("/v1/youtube/channel", {"handle": clean_handle}, api_key)
            if _positive_int(channel.get("subscriberCount")) is not None:
                break  # got a real positive count
            if attempt < _SUBS_RETRIES:
                time.sleep(_RETRY_BACKOFF * (2 ** attempt))
        record = _map_channel_basic(handle, channel)
        # Accept the count only if it's a real positive number; otherwise leave
        # it unknown (None) so the caller can route it to "needs verification"
        # rather than range-filtering a 0/guess.
        record["subscribers"] = _positive_int(channel.get("subscriberCount"))
        return record

    return _safe_live_fetch(handle, _inner)


def _search_channels_live(query, limit):
    """Search YouTube channels for a topic query, deduped and capped at limit.

    Returns a list of candidate dicts: {handle, channel_id, name, subs_hint}.
    Paginates with continuationToken until enough unique candidates are found.
    """
    api_key = _require_api_key()
    candidates = []
    seen = set()
    token = None
    for _ in range(_MAX_SEARCH_PAGES):
        params = {"query": query, "type": "channels"}
        if token:
            params["continuationToken"] = token
        page = _api_get("/v1/youtube/search", params, api_key)
        for ch in page.get("channels") or []:
            handle = ch.get("handle")
            channel_id = ch.get("id")
            key = channel_id or handle
            if not handle or not key or key in seen:
                continue
            seen.add(key)
            candidates.append({
                "handle": handle,
                "channel_id": channel_id,
                "name": ch.get("channelName"),
                "subs_hint": ch.get("subscriberCountInt"),
            })
            if len(candidates) >= limit:
                return candidates
        token = page.get("continuationToken")
        if not token or not (page.get("channels")):
            break
    return candidates


def fetch_creator(handle, live=False, months=None, max_videos=None):
    """Full creator fetch (channel + recent uploads + sponsors).

    Returns a record dict with keys: handle, name, platform, subscribers,
    audience_geo, recent_sponsors, verified, source, error, channel_country.

    ``months`` overrides the lookback window and ``max_videos`` caps how many
    in-window uploads are checked for sponsors (used by market mode for cost
    control). In mock mode (default) returns clearly-labeled sample data;
    with ``live=True`` it calls the real Scrape Creators YouTube API.
    """
    if live:
        return _fetch_live(handle, months=months, max_videos=max_videos)
    return _fetch_mock(handle, months=months)


def fetch_channel_profile(handle, live=False):
    """Lightweight channel-details fetch for SOURCE mode (no sponsor pull).

    One lookup per candidate: name, subscriber count, and the channel's own
    stated country. Leaves recent_sponsors and audience_geo empty.
    """
    if live:
        return _fetch_channel_live(handle)
    return _fetch_channel_mock(handle)


def search_channels(query, limit, live=False):
    """Find channel candidates for a topic query (deduped, capped at limit).

    Returns a list of {handle, channel_id, name, subs_hint} dicts.
    """
    if live:
        return _search_channels_live(query, limit)
    return _search_channels_mock(query, limit)


# ===========================================================================
# SHORT FORM: Instagram (fully wired) and TikTok (wired defensively).
#
# Confirmed from the docs + live checks:
#   IG  /v1/instagram/search/profiles?query=   -> profiles[] (discovery)
#   IG  /v2/instagram/user/posts?handle=        -> items[] with taken_at (unix),
#                                                  caption.text, is_paid_partnership
#   TT  /v1/tiktok/search/users?query=          -> users[] (often empty)
#   TT  /v1/tiktok/profile?handle=              -> itemList[] (often EMPTY)
#
# Neither platform returns a sponsor-brand-NAME field — only an is_paid_partnership
# flag. So short form is conservative: a brand is named ONLY when a post is
# flagged is_paid_partnership AND a known brand from config's lexicon appears in
# the caption. A hashtag alone is never enough. Everything else stays UNVERIFIED.
# TikTok's per-creator feed came back empty in live checks, so it yields little;
# we wire it per the docs rather than fabricate data.
# ===========================================================================
SHORT_FORM_MAX_PAGES = 5  # post pages to scan per creator before stopping


def _unix_to_date(ts):
    try:
        return datetime.utcfromtimestamp(int(ts)).strftime("%Y-%m-%d")
    except (ValueError, TypeError, OSError):
        return None


def _short_form_record(handle, platform):
    record = _empty_record(handle)
    record["platform"] = platform
    record["source"] = "Scrape Creators API (live)"
    return record


def _sponsors_from_caption(text, date, platform):
    """Conservative brand extraction: only known lexicon brands found in the
    caption of an already-confirmed paid-partnership post. Returns sponsor
    dicts (deduped by brand within the post)."""
    out = []
    seen = set()
    for pattern, _brief_cat in config.known_brands_in_text(text or ""):
        if pattern in seen:
            continue
        seen.add(pattern)
        out.append({
            "name": pattern,
            "category": None,
            "date": date,
            "confidence": "high",  # explicit paid-partnership flag + known brand
            "platform": platform,
        })
    return out


def _fetch_instagram_live(handle, months):
    api_key = _require_api_key()
    clean = handle.strip().lstrip("@")
    cutoff = datetime.utcnow() - timedelta(days=30 * months)

    def _inner():
        record = _short_form_record(handle, "Instagram")
        record["verified"] = True
        sponsors = []
        eng = []  # (likes, comments, plays) per in-window post
        next_max_id = None
        for _ in range(SHORT_FORM_MAX_PAGES):
            params = {"handle": clean}
            if next_max_id:
                params["next_max_id"] = next_max_id
            data = _api_get("/v2/instagram/user/posts", params, api_key)
            if record["name"] is None:
                record["name"] = (data.get("user") or {}).get("username") or clean
            items = data.get("items") or []
            reached_old = False
            for it in items:
                date = _unix_to_date(it.get("taken_at"))
                if date is None:
                    continue
                if datetime.strptime(date, "%Y-%m-%d") < cutoff:
                    reached_old = True
                    break
                eng.append((it.get("like_count"), it.get("comment_count"),
                            it.get("play_count") or it.get("ig_play_count")))
                # Only an explicit paid-partnership flag counts as a sponsor.
                if not (it.get("is_paid_partnership") or it.get("is_ad")):
                    continue
                caption = (it.get("caption") or {}).get("text", "")
                sponsors.extend(_sponsors_from_caption(caption, date, "Instagram"))
            next_max_id = data.get("next_max_id")
            if reached_old or not next_max_id or not items:
                break
        record["recent_sponsors"] = sponsors
        _apply_ig_engagement(record, eng)
        return record

    return _safe_live_fetch(handle, _inner)


def _fetch_tiktok_live(handle, months):
    api_key = _require_api_key()
    clean = handle.strip().lstrip("@")
    cutoff = datetime.utcnow() - timedelta(days=30 * months)

    def _inner():
        record = _short_form_record(handle, "TikTok")
        data = _api_get("/v1/tiktok/profile", {"handle": clean}, api_key)
        record["verified"] = True
        record["name"] = (data.get("user") or {}).get("nickname") or clean
        sponsors = []
        # itemList is the documented recent-videos array (empty in practice).
        for it in data.get("itemList") or []:
            ts = it.get("createTime") or it.get("create_time")
            date = _unix_to_date(ts)
            if date is None or datetime.strptime(date, "%Y-%m-%d") < cutoff:
                continue
            if not (it.get("is_paid_partnership") or it.get("isAd") or it.get("is_ad")):
                continue
            caption = it.get("desc", "")
            sponsors.extend(_sponsors_from_caption(caption, date, "TikTok"))
        record["recent_sponsors"] = sponsors
        return record

    return _safe_live_fetch(handle, _inner)


def _search_instagram_live(query, limit):
    api_key = _require_api_key()
    handles, seen = [], set()
    cursor = None
    for _ in range(_MAX_SEARCH_PAGES):
        params = {"query": query}
        if cursor:
            params["cursor"] = cursor
        page = _api_get("/v1/instagram/search/profiles", params, api_key)
        for p in page.get("profiles") or []:
            h = p.get("handle") or p.get("username") or (p.get("user") or {}).get("username")
            if not h or h.lower() in seen:
                continue
            seen.add(h.lower())
            handles.append({"handle": h, "name": p.get("full_name"), "platform": "Instagram"})
            if len(handles) >= limit:
                return handles
        cursor = page.get("cursor")
        if not cursor or not (page.get("profiles")):
            break
    return handles


def _search_tiktok_live(query, limit):
    api_key = _require_api_key()
    handles, seen = [], set()
    cursor = None
    for _ in range(_MAX_SEARCH_PAGES):
        params = {"query": query}
        if cursor:
            params["cursor"] = cursor
        page = _api_get("/v1/tiktok/search/users", params, api_key)
        for u in page.get("users") or []:
            ui = u.get("user_info") or u
            h = ui.get("unique_id") or ui.get("uniqueId")
            if not h or h.lower() in seen:
                continue
            seen.add(h.lower())
            handles.append({"handle": h, "name": ui.get("nickname"), "platform": "TikTok"})
            if len(handles) >= limit:
                return handles
        cursor = page.get("cursor")
        if not cursor or not (page.get("users")):
            break
    return handles


# ---------------------------------------------------------------------------
# MOCK football data for RADAR mode (so mock shows the full multi-platform
# shape: brief categories, gambling exclusion, borderline review, roster
# conflict/fit, live vs evergreen, and a TikTok that honestly yields nothing).
# Sponsor tuples: (brand, months_ago, confidence). months_ago 0-1 -> LIVE.
# ---------------------------------------------------------------------------
_MOCK_RADAR = {
    "YouTube": {
        "footyadventures": {"name": "Footy Adventures (SAMPLE)", "subs": 238000, "sponsors": [
            ("NordVPN", 0, "high"), ("Nike", 1, "high"),
            ("Bet365", 1, "high"),        # gambling -> hard dropped
            ("Sleeper", 2, "medium")]},   # borderline -> excluded for review
        "number9": {"name": "Number 9 (SAMPLE)", "subs": 104000, "sponsors": [
            ("adidas", 3, "high"), ("Red Bull", 2, "medium")]},
        "vizeh": {"name": "Vizeh (SAMPLE)", "subs": 490000, "sponsors": [
            ("EA Sports FC", 1, "high"),
            ("Coinbase", 2, "high")]},     # borderline -> excluded for review
        "footebate": {"name": "Footebate (SAMPLE)", "subs": 207000, "sponsors": [
            ("DAZN", 4, "high")]},
        "hrvizak": {"name": "HRVizak (SAMPLE)", "subs": 291000, "sponsors": [
            ("Samsung", 2, "high")]},
        "fiago": {"name": "Fiago (SAMPLE)", "subs": 847000, "sponsors": [
            ("EA Sports FC", 0, "high"), ("Red Bull", 1, "high")]},
        "stuntpegg": {"name": "StuntPegg (SAMPLE)", "subs": 472000, "sponsors": [
            ("Manscaped", 5, "high"),
            ("Bet365 Casino", 1, "high")]},  # gambling -> hard dropped
        "soccerstatsdaily": {"name": "Soccer Stats Daily (SAMPLE)", "subs": 60000, "sponsors": [
            ("NordVPN", 1, "high"), ("Nike", 9, "high")]},  # Nike here is >6mo -> dropped
        # Two large (>1M) discovered creators: a non-mega brand on both shows
        # the LIKELY AGENCY by creator-mix path (Surfshark, not on mega list).
        "globalfootballtv": {"name": "Global Football TV (SAMPLE)", "subs": 3200000, "sponsors": [
            ("Surfshark", 1, "high")]},
        "worldsoccerhd": {"name": "World Soccer HD (SAMPLE)", "subs": 1800000, "sponsors": [
            ("Surfshark", 2, "high")]},
    },
    "Instagram": {
        "hrvizak": {"name": "HRVizak (SAMPLE)", "subs": 325000, "sponsors": [("adidas", 1, "high")]},
        "footy.skills": {"name": "Footy Skills (SAMPLE)", "subs": 150000, "sponsors": [
            ("Nike", 2, "high"), ("Prime Hydration", 0, "high")]},
    },
    "TikTok": {
        # TikTok returns no usable per-creator feed in practice -> no sponsors.
        "hrvizak": {"name": "HRVizak (SAMPLE)", "subs": 410000, "sponsors": []},
    },
}


def _radar_fetch_mock(handle, platform, months):
    record = _empty_record(handle)
    record["platform"] = platform
    record["source"] = "MOCK (sample data — not real)"
    data = (_MOCK_RADAR.get(platform) or {}).get(handle.strip().lower().lstrip("@"))
    if data is None:
        return record
    record["name"] = data.get("name")
    record["subscribers"] = data.get("subs")
    sponsors = []
    for brand, months_ago, conf in data.get("sponsors") or []:
        if months is not None and months_ago > months:
            continue
        sponsors.append({
            "name": brand, "category": None, "date": _months_ago(months_ago),
            "confidence": conf, "platform": platform,
        })
    record["recent_sponsors"] = sponsors
    if platform == "Instagram" and isinstance(record["subscribers"], int):
        subs = record["subscribers"]
        _apply_ig_engagement(record, [(int(subs * 0.06), int(subs * 0.004), None)] * 6)
    else:
        _mock_view_metrics(record)
    return record


def _radar_search_mock(platform, limit):
    handles = list((_MOCK_RADAR.get(platform) or {}).keys())[:limit]
    return [{"handle": h, "platform": platform} for h in handles]


def radar_fetch(handle, platform, live=False, months=6, max_videos=None):
    """Fetch one creator's recent sponsors on a given platform for radar mode."""
    platform = platform.strip().lower()
    if platform in ("youtube", "yt"):
        if live:
            return _fetch_live(handle, months=months, max_videos=max_videos)
        return _fetch_mock(handle, months=months) if handle.strip().lower().lstrip("@") in _MOCK_CREATORS \
            else _radar_fetch_mock(handle, "YouTube", months)
    if platform in ("instagram", "ig"):
        if live:
            return _fetch_instagram_live(handle, months)
        return _radar_fetch_mock(handle, "Instagram", months)
    if platform in ("tiktok", "tt"):
        if live:
            return _fetch_tiktok_live(handle, months)
        return _radar_fetch_mock(handle, "TikTok", months)
    raise ValueError(f"Unknown platform: {platform!r}")


def radar_search(query, platform, limit, live=False):
    """Find creator handles for a topic query on a given platform."""
    platform = platform.strip().lower()
    if platform in ("youtube", "yt"):
        if live:
            return [{"handle": c["handle"], "platform": "YouTube"}
                    for c in _search_channels_live(query, limit)]
        return _radar_search_mock("YouTube", limit)
    if platform in ("instagram", "ig"):
        if live:
            return _search_instagram_live(query, limit)
        return _radar_search_mock("Instagram", limit)
    if platform in ("tiktok", "tt"):
        if live:
            return _search_tiktok_live(query, limit)
        return _radar_search_mock("TikTok", limit)
    raise ValueError(f"Unknown platform: {platform!r}")
