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
from datetime import datetime, timedelta

import config

# Live Scrape Creators API settings.
BASE_URL = "https://api.scrapecreators.com"
API_KEY_ENV = "SCRAPECREATORS_API_KEY"

# Safety caps so a single creator can never trigger unbounded API spend.
_MAX_VIDEO_PAGES = 5        # pages of channel uploads to scan, newest first
_MAX_SPONSOR_LOOKUPS = 40   # in-window videos to query for sponsors


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
# Pipeline per creator handle:
#   1. GET /v1/youtube/channel        -> name + subscriberCount + channelId
#   2. GET /v1/youtube/channel-videos -> recent uploads with publish dates
#   3. GET /v1/youtube/video/sponsors -> brand names for each in-window upload
#
# Auth is the x-api-key header read from the SCRAPECREATORS_API_KEY env var.
# We set verified=True only when the channel lookup actually returns data, map
# only fields the API returns (missing ones stay empty), and deliberately do
# NOT populate audience_geo — Scrape Creators does not expose YouTube
# audience-location data, so geo reads UNKNOWN rather than us inventing it.
# Any 401 / 402 / failed lookup for one creator is caught and turned into an
# UNVERIFIED record so the rest of the batch keeps running.
# ===========================================================================
def _fetch_live(handle):
    """Fetch a creator from the real Scrape Creators YouTube API."""
    import requests  # imported lazily so mock mode never needs requests

    api_key = os.environ.get(API_KEY_ENV)
    if not api_key:
        # A totally missing key is a configuration problem, not a per-creator
        # one, so fail fast with a clear message instead of producing a report
        # full of identical errors.
        raise RuntimeError(
            f"Live mode requested but {API_KEY_ENV} is not set. Export your "
            "Scrape Creators API key, or run without --live to use mock data."
        )

    def api_get(path, params):
        resp = requests.get(
            BASE_URL + path,
            params=params,
            headers={"x-api-key": api_key},
            timeout=30,
        )
        if resp.status_code == 401:
            raise _CreatorLookupError(
                f"API auth failed (401) — check {API_KEY_ENV}."
            )
        if resp.status_code == 402:
            raise _CreatorLookupError(
                "API payment required (402) — account out of credits."
            )
        if resp.status_code == 404:
            raise _CreatorLookupError("Creator/video not found (404).")
        resp.raise_for_status()
        return resp.json()

    clean_handle = handle.strip().lstrip("@")

    try:
        # --- 1. Channel details -------------------------------------------
        channel = api_get("/v1/youtube/channel", {"handle": clean_handle})

        record = _empty_record(handle)
        record["source"] = "Scrape Creators API (live)"
        # The channel lookup succeeded, so the fields we map below are real.
        record["verified"] = True
        record["platform"] = "YouTube"
        # Map only fields the API actually returned; missing ones stay empty.
        if channel.get("name"):
            record["name"] = channel["name"]
        if channel.get("subscriberCount") is not None:
            record["subscribers"] = channel["subscriberCount"]
        channel_id = channel.get("channelId")
        # audience_geo intentionally left empty (see header note).

        # --- 2. Recent uploads inside the lookback window -----------------
        cutoff = datetime.utcnow() - timedelta(days=30 * config.LOOKBACK_MONTHS)
        in_window = []  # list of {"url", "date"} for videos within the window
        token = None
        for _ in range(_MAX_VIDEO_PAGES):
            if channel_id:
                params = {"channelId": channel_id}
            else:
                params = {"handle": clean_handle}
            if token:
                params["continuationToken"] = token

            page = api_get("/v1/youtube/channel-videos", params)
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
            data = api_get("/v1/youtube/video/sponsors", {"url": vid["url"]})
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

    except _CreatorLookupError as e:
        return _live_error_record(handle, str(e))
    except requests.RequestException as e:
        return _live_error_record(handle, f"Network/API error: {e}")
    except Exception as e:  # noqa: BLE001 - never let one creator kill the batch
        return _live_error_record(handle, f"Unexpected error: {e}")


def fetch_creator(handle, live=False):
    """Fetch a single creator by handle.

    Returns a record dict with keys: handle, name, platform, subscribers,
    audience_geo, recent_sponsors, verified, source, error.

    In mock mode (default) returns clearly-labeled sample data. With
    ``live=True`` it calls the real Scrape Creators YouTube API.
    """
    if live:
        return _fetch_live(handle)
    return _fetch_mock(handle)
