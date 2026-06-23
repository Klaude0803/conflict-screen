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


def _fetch_live(handle):
    """Fetch a creator from the real Scrape Creators API.

    ===================================================================
    WIRE THE LIVE SCRAPE CREATORS API HERE.
    ===================================================================
    Read your API key from the environment (do not hard-code it):

        api_key = os.environ.get("SCRAPE_CREATORS_API_KEY")

    Then call the API (e.g. with ``requests``), map the response into the
    record skeleton from ``_empty_record``, and set ``verified=True`` ONLY
    for fields the API actually returned. Leave anything missing empty —
    never fill gaps with guesses.

    Example skeleton (pseudo-code, adapt to the real endpoints):

        import requests
        resp = requests.get(
            "https://api.scrapecreators.com/v1/creator",
            params={"handle": handle},
            headers={"x-api-key": api_key},
            timeout=30,
        )
        resp.raise_for_status()
        payload = resp.json()

        record = _empty_record(handle)
        record["source"] = "Scrape Creators API (live)"
        record["name"] = payload.get("name")          # stays None if absent
        record["platform"] = payload.get("platform")
        record["subscribers"] = payload.get("subscriber_count")
        record["audience_geo"] = payload.get("audience_geo", {})
        record["recent_sponsors"] = [
            {"name": s["name"], "category": s.get("category"), "date": s.get("date")}
            for s in payload.get("sponsors", [])
        ]
        record["verified"] = True
        return record
    ===================================================================
    """
    api_key = os.environ.get("SCRAPE_CREATORS_API_KEY")
    if not api_key:
        raise RuntimeError(
            "Live mode requested but SCRAPE_CREATORS_API_KEY is not set, and "
            "the live API call has not been wired up yet. See _fetch_live in "
            "src/scrape_client.py. Run without --live to use mock data."
        )
    raise NotImplementedError(
        "The live Scrape Creators API call is not wired up yet. "
        "Implement the marked section in _fetch_live in src/scrape_client.py."
    )


def fetch_creator(handle, live=False):
    """Fetch a single creator by handle.

    Returns a record dict with keys: handle, name, platform, subscribers,
    audience_geo, recent_sponsors, verified, source.

    In mock mode (default) returns clearly-labeled sample data. With
    ``live=True`` it calls the real API (which you must wire up first).
    """
    if live:
        return _fetch_live(handle)
    return _fetch_mock(handle)
