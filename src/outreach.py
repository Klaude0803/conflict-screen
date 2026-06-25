"""Outreach mode: draft a cold email to a brand from a market-radar row.

DRAFTS ONLY. This module generates text — it never sends anything and has no
integration with any email or sending service. Output is a local file labeled
as a draft for human review.

The copy is generated from deterministic templates so the hard constraints are
guaranteed: subject lines under 60 characters, no ASCII hyphens anywhere in the
subjects or body (em dashes are fine), a body of 75 to 110 words, and exactly
one call to action. We validate every draft against these rules before writing.
"""

from datetime import datetime

DRAFT_LABEL = "DRAFT — review before sending"

# Phrases the body must never contain (case-insensitive): no "I run an agency"
# and nothing that describes a backend process.
_FORBIDDEN = [
    "i run an agency", "my agency", "our agency", "run an agency",
    "my team", "our team", "our process", "we scrape", "backend",
    "automated", "automation", "our system", "our tool", "our software",
]


def _clean_handle(handle):
    """Normalize a creator handle for display: drop a leading @, strip spaces,
    and remove hyphens so the no-hyphen rule always holds."""
    return handle.strip().lstrip("@").replace("-", "").strip()


def _format_recent(recent):
    """Turn a placement date into a hyphen-free human phrase (e.g. June 2026)."""
    if not recent:
        return "recent months"
    text = str(recent).strip()
    for fmt in ("%Y-%m-%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(text, fmt).strftime("%B %Y")
        except ValueError:
            continue
    # Last resort: never leave a hyphen in.
    return text.replace("-", " ")


def _creator_phrase(handles):
    """Render up to two example creators as proof, hyphen-free."""
    cleaned = [f"@{_clean_handle(h)}" for h in handles if _clean_handle(h)]
    if len(cleaned) >= 2:
        return f"people like {cleaned[0]} and {cleaned[1]}"
    if len(cleaned) == 1:
        return f"people like {cleaned[0]}"
    return "the bigger channels in this space"


def _subject_options(brand):
    """Three curiosity-driven subjects, each under 60 chars, no hyphens."""
    candidates = [
        f"{brand} keeps showing up lately",
        f"Noticed what {brand} is doing with creators",
        f"A quick read on {brand}",
        # Fallbacks in case a very long brand name pushes one over 60.
        f"Something about {brand}",
        "A quiet pattern worth a look",
    ]
    chosen = []
    for s in candidates:
        if "-" in s or len(s) >= 60:
            continue
        chosen.append(s)
        if len(chosen) == 3:
            break
    return chosen


def _body(brand, category, recent, handles):
    """One email body, 75 to 110 words, no hyphens, exactly one CTA."""
    niche = (category or "this niche").strip()
    proof = _creator_phrase(handles)
    when = _format_recent(recent)

    body = (
        f"Hi {brand} team,\n\n"
        f"I have been watching how {brand} keeps surfacing across {niche} "
        f"creators, and the pattern is clear. Placements with {proof} run into "
        f"{when}, so someone there already treats creators as a real channel, "
        f"not a test.\n\n"
        f"I spend my days close to creators in exactly this lane, so I hear "
        f"early where {brand} lands well and where it leaves money on the "
        f"table. That view might be useful to you, or it might not.\n\n"
        f"Either way there is no pressure. Worth a short conversation this "
        f"week?\n\n"
        f"Best,\nYour name"
    )
    return body


def _word_count(body):
    # Count the words a reader sees in the message body.
    return len(body.split())


def build_draft(brand, category=None, recent=None, creators=None):
    """Build and validate an outreach draft for a brand.

    Returns {"brand", "subjects", "body", "word_count"}. Raises ValueError if
    a generated draft breaks any of the hard constraints (a safety net so we
    never write a non-compliant draft).
    """
    brand = (brand or "").strip()
    if not brand:
        raise ValueError("A brand name is required to draft outreach.")
    handles = creators or []

    subjects = _subject_options(brand)
    body = _body(brand, category, recent, handles)

    # --- Validate the hard constraints before returning ------------------
    for s in subjects:
        if "-" in s:
            raise ValueError(f"Subject contains a hyphen: {s!r}")
        if len(s) >= 60:
            raise ValueError(f"Subject is 60+ chars: {s!r} ({len(s)})")
    if len(subjects) != 3:
        raise ValueError(f"Expected 3 subject options, got {len(subjects)}.")

    if "-" in body:
        raise ValueError("Body contains a hyphen.")
    wc = _word_count(body)
    if not (75 <= wc <= 110):
        raise ValueError(f"Body word count {wc} is outside 75 to 110.")
    if body.count("?") != 1:
        raise ValueError("Body must contain exactly one call to action (one '?').")
    low = body.lower()
    for phrase in _FORBIDDEN:
        if phrase in low:
            raise ValueError(f"Body contains a forbidden phrase: {phrase!r}")

    return {"brand": brand, "subjects": subjects, "body": body, "word_count": wc}


def render_draft_text(draft, category=None, recent=None, creators=None):
    """Render the draft to a clean, clearly-labeled text document."""
    lines = []
    lines.append("=" * 60)
    lines.append(DRAFT_LABEL)
    lines.append("This file was drafted locally. Nothing has been sent.")
    lines.append("=" * 60)
    lines.append("")
    lines.append(f"Brand:    {draft['brand']}")
    if category:
        lines.append(f"Category: {category}")
    if recent:
        lines.append(f"Recent placement: {recent}")
    if creators:
        shown = ", ".join(f"@{_clean_handle(h)}" for h in creators if _clean_handle(h))
        lines.append(f"Example creators: {shown}")
    lines.append("")
    lines.append("SUBJECT LINE OPTIONS (pick one):")
    for i, s in enumerate(draft["subjects"], start=1):
        lines.append(f"  {i}. {s}")
    lines.append("")
    lines.append(f"EMAIL BODY ({draft['word_count']} words):")
    lines.append("")
    lines.append(draft["body"])
    lines.append("")
    lines.append("=" * 60)
    lines.append(f"{DRAFT_LABEL}. Not sent. Review and send manually.")
    lines.append("=" * 60)
    return "\n".join(lines)


def write_draft(draft, out_path, category=None, recent=None, creators=None):
    """Write the rendered draft to a local text file."""
    text = render_draft_text(draft, category=category, recent=recent, creators=creators)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(text)
    return out_path
