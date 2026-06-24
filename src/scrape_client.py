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
            {"name": "NordVPN", "category": "vpn", "months_ago": 3},
            {"name": "Squarespace", "category": "website_builder", "months_ago": 7},
        ],
    },
    "gadgetguygreg": {
        "name": "Gadget Greg (SAMPLE)",
        "platform": "YouTube",
        "subscribers": 540000,
        "audience_geo": {"US": 22, "IN": 31, "BR": 18, "GB": 6, "CA": 3, "PH": 20},
        "recent_sponsors": [
            {"name": "Squarespace", "category": "website_builder", "months_ago": 2},
            {"name": "Honey", "category": "shopping", "months_ago": 5},
        ],
    },
    "privacypaula": {
        "name": "Privacy Paula (SAMPLE)",
        "platform": "YouTube",
        "subscribers": 320000,
        "audience_geo": {"US": 55, "CA": 14, "GB": 11, "AU": 8, "DE": 12},
        "recent_sponsors": [
            # An old VPN deal, just outside the 12-month window.
            {"name": "ExpressVPN", "category": "vpn", "months_ago": 15},
        ],
    },
    "lifestyleliam": {
        "name": "Lifestyle Liam (SAMPLE)",
        "platform": "Instagram",
        "subscribers": 89000,
        "audience_geo": {"US": 30, "GB": 9, "CA": 5, "AU": 4, "FR": 22, "ES": 30},
        "recent_sponsors": [
            {"name": "HelloFresh", "category": "meal_kit", "months_ago": 4},
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
}


def _fetch_mock(handle):
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
        sponsors.append({
            "name": s["name"],
            "category": s.get("category"),
            "date": _months_ago(s["months_ago"]),
        })
    record["recent_sponsors"] = sponsors
    # Mock data is sample data, so it is NOT verified.
    record["verified"] = False
    return record


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


def _fetch_live(handle):
    """Full screen-mode fetch: channel -> videos -> sponsors."""
    api_key = _require_api_key()
    clean_handle = handle.strip().lstrip("@")

    def _inner():
        # --- 1. Channel details -------------------------------------------
        channel = _api_get("/v1/youtube/channel", {"handle": clean_handle}, api_key)
        record = _map_channel_basic(handle, channel)
        channel_id = channel.get("channelId")

        # --- 2. Recent uploads inside the lookback window -----------------
        cutoff = datetime.utcnow() - timedelta(days=30 * config.LOOKBACK_MONTHS)
        in_window = []  # list of {"url", "date"} for videos within the window
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
                if v.get("url"):
                    in_window.append({
                        "url": v["url"],
                        "date": published.strftime("%Y-%m-%d"),
                    })

            token = page.get("continuationToken")
            if reached_old or not token or not videos:
                break

        # --- 3. Sponsors for each in-window upload ------------------------
        sponsors = []
        for vid in in_window[:_MAX_SPONSOR_LOOKUPS]:
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
                })
        record["recent_sponsors"] = sponsors
        return record

    return _safe_live_fetch(handle, _inner)


def _fetch_channel_live(handle):
    """Lightweight source-mode fetch: channel details + country only.

    Exactly one API lookup per candidate (predictable spend). Sponsor history
    is NOT pulled here, so the conflict screen will report UNVERIFIED unless a
    record already carries confirmed sponsors — by design, sourcing is a cheap
    discovery pass; run screen mode on the shortlist for full CONFLICT/CLEAR
    verdicts.
    """
    api_key = _require_api_key()
    clean_handle = handle.strip().lstrip("@")

    def _inner():
        channel = _api_get("/v1/youtube/channel", {"handle": clean_handle}, api_key)
        return _map_channel_basic(handle, channel)

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


def fetch_creator(handle, live=False):
    """Full creator fetch for SCREEN mode (channel + videos + sponsors).

    Returns a record dict with keys: handle, name, platform, subscribers,
    audience_geo, recent_sponsors, verified, source, error, channel_country.

    In mock mode (default) returns clearly-labeled sample data. With
    ``live=True`` it calls the real Scrape Creators YouTube API.
    """
    if live:
        return _fetch_live(handle)
    return _fetch_mock(handle)


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
