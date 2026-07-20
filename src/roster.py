"""Roster enrichment + the shareable two-line roster output (Elite Edge).

Adds the creator-side, non-fabricated layers on top of a fetched record:
narrative role (rules-based from niche tags), recurring-revenue fit flags,
a brand-safety note (AI/avatar + FTC always flagged for human review, never
auto-asserted), and an evergreen/search signal always labeled heuristic-only.

Hard rules honored here:
  - Stated channel country is NEVER treated as audience US%. US audience % is
    private analytics -> always NOT FOUND until a source is connected.
  - Average view duration, connected-TV share, TikTok Shop GMV -> NOT FOUND
    (pending: direct creator requests; Sponsorship.so MCP evaluation).
  - No rates, no brand economics. Creator-side facts only.
"""

NOT_FOUND = "NOT FOUND"

# Fields that are structurally NOT FOUND from the current pipeline (private
# analytics). Kept NOT FOUND — never estimated — until a source is connected.
PENDING_NOT_FOUND = [
    "US audience concentration (pending: direct creator requests; Sponsorship.so MCP eval)",
    "Average view duration (pending: direct creator requests)",
    "Connected-TV / TV-screen share (pending: direct creator requests)",
    "TikTok Shop GMV / conversion (no source wired)",
]

# Rules-based narrative role from a creator's niche tag words, in priority order.
_ROLE_RULES = [
    ("authority", {"finance", "tech", "educational", "science", "news",
                   "geopolitics", "analysis", "intellectual", "productivity"}),
    ("cultural commentator", {"commentary", "culture", "history", "politics",
                              "debate", "opinion", "interviews", "reactions"}),
    ("lifestyle translator", {"lifestyle", "home", "wellness", "health",
                              "travel", "ev", "design", "study"}),
    ("short-form amplifier", {"shorts", "tiktok", "clips", "highlights",
                              "shortform", "viral", "amplifier"}),
    ("niche community", {"gaming", "mma", "football", "sports", "hobby",
                         "community", "fifa", "esports"}),
]


def _tag_words(tags):
    words = set()
    for t in tags or []:
        for w in "".join(c if c.isalnum() else " " for c in t.lower()).split():
            words.add(w)
    return words


def narrative_role(tags):
    """One narrative role from the supplied niche tags (rules-based). NOT FOUND
    when no tag maps — never guessed."""
    words = _tag_words(tags)
    for role, keys in _ROLE_RULES:
        if words & keys:
            return role
    return NOT_FOUND


def recurring_fit_flags(record):
    """Opportunity flags for recurring structures (no rates). Whitelisting
    depends on creator permission the API can't see, so it's flagged to confirm,
    never asserted."""
    runs_deals = bool(record.get("recent_sponsors"))
    always_on = "candidate" if runs_deals else "unproven (no recent deals seen)"
    return [
        f"always-on/dedicated section: {always_on}",
        "whitelisting/paid usage: confirm with creator (permission NOT FOUND)",
        "licensing/repurposing: candidate, confirm rights",
    ]


def brand_safety_note(record):
    """Brand-safety note. AI/avatar-vs-real and FTC disclosure need human/visual
    review and are FLAGGED, never auto-asserted (the API gives no reliable
    signal). Approvability is pending that review."""
    return ("AI/real: manual review needed, deprioritize if AI/avatar-heavy; "
            "FTC/disclosure: manual review; approvability: pending review")


def evergreen_signal(record):
    """Evergreen / search discoverability — HEURISTIC ONLY, never a hard metric.
    Older uploads still accruing views is a hint, not a number."""
    return "heuristic only (not a confirmed metric)"


def _fmt_int(v):
    return f"{v:,}" if isinstance(v, int) else NOT_FOUND


def _consistency_str(record):
    vc = record.get("view_consistency")
    if not vc:
        return NOT_FOUND
    cov = vc.get("cov")
    tail = f", cov {cov}" if cov is not None else ""
    return f"{vc.get('label')} ({vc.get('n')} uploads{tail})"


def _engagement_str(record):
    e = record.get("engagement")
    if not e:
        return NOT_FOUND
    likes = _fmt_int(e.get("avg_likes"))
    comments = _fmt_int(e.get("avg_comments"))
    return f"~{likes} likes / ~{comments} comments per post ({e.get('note')})"


def enrich(record, tags, conflict_status):
    """Assemble the roster fields for one creator (creator-side facts only)."""
    handle = record.get("handle") or ""
    platform = record.get("platform") or NOT_FOUND
    niche = ", ".join(tags) if tags else NOT_FOUND
    contact = f"{platform}: @{handle}" if handle else NOT_FOUND
    return {
        "name": record.get("name") or handle or NOT_FOUND,
        "platform": platform,
        "niche": niche,
        "subs": _fmt_int(record.get("subscribers")),
        "recent_avg_views": _fmt_int(record.get("recent_avg_views")),
        "view_consistency": _consistency_str(record),
        "engagement": _engagement_str(record),
        # US % is private analytics — NEVER the stated channel country.
        "us_pct": NOT_FOUND,
        "avd": NOT_FOUND,          # average view duration — private analytics
        "ctv": NOT_FOUND,          # connected-TV share — private analytics
        "stated_country": record.get("channel_country") or NOT_FOUND,
        "narrative_role": narrative_role(tags),
        "recurring_fit": recurring_fit_flags(record),
        "brand_safety": brand_safety_note(record),
        "evergreen": evergreen_signal(record),
        "conflict_status": conflict_status,
        "contact": contact,
        "verified": bool(record.get("verified")) and not record.get("error"),
        "error": record.get("error"),
    }


def render_roster(entries, brand=None):
    """Render the shareable two-line roster. No rates, no brand economics."""
    lines = []
    lines.append("=" * 72)
    lines.append("SHAREABLE ROSTER — creator-side facts only, no rates/economics")
    if brand:
        lines.append(f"Conflict-screened against: {brand} (12-month competitor check)")
    lines.append("Hand off to Melly to route. Stated country is NOT audience US%.")
    lines.append("=" * 72)
    lines.append("")

    conflicts = 0
    for e in entries:
        if e.get("error"):
            lines.append(f"{e['name']}  [UNVERIFIED — {e['error']}]")
            lines.append(f"    contact: {e['contact']}  | all fields: {NOT_FOUND}")
            lines.append("")
            continue
        if str(e["conflict_status"]).startswith("CONFLICT"):
            conflicts += 1
        # Line 1: name, platform, niche, subs, recent avg views, US %, role
        lines.append(
            f"{e['name']} | {e['platform']} | {e['niche']} | subs {e['subs']} | "
            f"recent avg views {e['recent_avg_views']} | US% {e['us_pct']} | "
            f"role: {e['narrative_role']}"
        )
        # Line 2: AVD/CTV if found, brand-safety, conflict, recurring-fit, contact
        lines.append(
            f"    AVD {e['avd']} / CTV {e['ctv']} | consistency: {e['view_consistency']} | "
            f"engagement: {e['engagement']} | evergreen: {e['evergreen']} | "
            f"brand-safety: {e['brand_safety']} | conflict: {e['conflict_status']} | "
            f"recurring-fit: {'; '.join(e['recurring_fit'])} | {e['contact']}"
        )
        lines.append("")

    # Close with totals + the NOT FOUND fields.
    lines.append("=" * 72)
    lines.append(f"Total sourced: {len(entries)}   |   Conflicts flagged: {conflicts}")
    lines.append("Fields returned NOT FOUND (private analytics — never estimated):")
    for f in PENDING_NOT_FOUND:
        lines.append(f"  - {f}")
    lines.append("AI/avatar and FTC disclosure: flagged for human review, not auto-asserted.")
    lines.append("Evergreen/search signal: heuristic only.")
    lines.append("Handed to Melly to route.")
    lines.append("=" * 72)
    return "\n".join(lines)
