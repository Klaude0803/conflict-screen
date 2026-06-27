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

# Lazy follow-up openers a calm operator never uses. Every touch must lead
# with something genuinely new instead.
_FORBIDDEN_FOLLOWUP = [
    "just checking in", "checking in", "circling back", "circle back",
    "bumping this", "bump this", "following up", "touching base",
    "any update", "did you see", "just wanted to", "as promised",
]

# Fake urgency / invented scarcity — banned everywhere.
_URGENCY = [
    "act now", "limited time", "last chance", "don't miss", "dont miss",
    "only a few", "spots left", "spots are", "deadline", "expires",
    "hurry", "urgent", "running out", "before it is gone", "act fast",
    "final call",
]


def _check_copy(text, *, words=None, allow_followup_openers=False):
    """Validate one piece of email copy against the hard rules.

    Raises ValueError on any violation: ASCII hyphen, wrong CTA count (must be
    exactly one '?'), a forbidden / lazy-follow-up / urgency phrase, or (when
    ``words`` is a (lo, hi) tuple) a word count outside that range.
    """
    if "-" in text:
        raise ValueError("Copy contains a hyphen.")
    if text.count("?") != 1:
        raise ValueError("Copy must contain exactly one call to action (one '?').")
    low = text.lower()
    banned = list(_FORBIDDEN) + list(_URGENCY)
    if not allow_followup_openers:
        banned += _FORBIDDEN_FOLLOWUP
    for phrase in banned:
        if phrase in low:
            raise ValueError(f"Copy contains a forbidden phrase: {phrase!r}")
    if words is not None:
        lo, hi = words
        wc = _word_count(text)
        if not (lo <= wc <= hi):
            raise ValueError(f"Copy word count {wc} is outside {lo} to {hi}.")


def _display_name(handle):
    """Render a creator as a plain channel name for the body copy.

    Drops any leading @, turns hyphens into spaces (so "VPN-Reviews" reads as
    "VPN Reviews"), and collapses whitespace. Never an @handle, never a hyphen.
    """
    name = handle.strip().lstrip("@").replace("-", " ")
    return " ".join(name.split())


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


def _creator_names(handles):
    """Plain display names for the supplied creators (no @, no hyphens)."""
    return [_display_name(h) for h in handles if _display_name(h)]


def _join_names(names):
    """Join up to three plain names: 'A', 'A and B', or 'A, B and C'."""
    names = names[:3]
    if len(names) >= 3:
        return f"{names[0]}, {names[1]} and {names[2]}"
    if len(names) == 2:
        return f"{names[0]} and {names[1]}"
    if len(names) == 1:
        return names[0]
    return "the bigger channels in this space"


def _creator_phrase(handles):
    """Render up to three example creators as proof, by plain name."""
    names = _creator_names(handles)
    if not names:
        return "the bigger channels in this space"
    return f"people like {_join_names(names)}"


def _proof_sentence(names, when, proof_count):
    """A concrete proof sentence leading with what the creators are running."""
    joined = _join_names(names)
    if len(names) >= 2:
        verb = "have all run it" if len(names) >= 3 else "have both run it"
    elif len(names) == 1:
        verb = "is running it"
    else:
        return f"The cadence runs right into {when}."
    if proof_count:
        return f"{joined} {verb}, {proof_count} placements in {when} alone."
    return f"{joined} {verb}, with the pace picking up into {when}."


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


def _space_word(audience, category):
    """The space the CREATORS are in (e.g. football), not the brand category."""
    return (audience or category or "this space").strip()


def _body(brand, category, recent, handles, audience=None, proof_count=None):
    """Opener body, 75 to 110 words, no hyphens, exactly one CTA. Leads with
    what the brand is already doing with the creators, not the sender."""
    space = _space_word(audience, category)
    names = _creator_names(handles)
    when = _format_recent(recent)
    proof = _proof_sentence(names, when, proof_count)

    body = (
        f"Hi {brand} team,\n\n"
        f"{brand} is already live across {space} right now, and the cadence is "
        f"hard to miss. {proof} That reads less like a test and more like "
        f"someone there already treating creators as a real channel.\n\n"
        f"I spend my days close to {space} creators, so I tend to see where "
        f"{brand} lands well and where it leaves reach on the table. That view "
        f"might be useful to you, or it might not.\n\n"
        f"No pressure either way. Worth a short conversation this week?\n\n"
        f"Best,\nYour name"
    )
    return body


def _word_count(body):
    # Count the words a reader sees in the message body.
    return len(body.split())


def build_draft(brand, category=None, recent=None, creators=None,
                audience=None, proof_count=None):
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
    body = _body(brand, category, recent, handles, audience=audience,
                 proof_count=proof_count)

    # --- Validate the hard constraints before returning ------------------
    for s in subjects:
        if "-" in s:
            raise ValueError(f"Subject contains a hyphen: {s!r}")
        if len(s) >= 60:
            raise ValueError(f"Subject is 60+ chars: {s!r} ({len(s)})")
    if len(subjects) != 3:
        raise ValueError(f"Expected 3 subject options, got {len(subjects)}.")

    _check_copy(body, words=(75, 110))
    return {"brand": brand, "subjects": subjects, "body": body,
            "word_count": _word_count(body)}


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
        shown = ", ".join(_creator_names(creators))
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


# ===========================================================================
# SIX TOUCH FOLLOW UP SEQUENCE (still DRAFT ONLY — nothing is ever sent).
#
# Touch 1 opens the thread with a spicy, curiosity-driven subject. Touches 2
# through 6 reply in thread under a plain "re: ..." subject, because clarity
# beats cleverness on follow ups. Every touch leads with something genuinely
# new, carries exactly one CTA, and uses plain creator names (no @ handles)
# and no hyphens.
# ===========================================================================
def _touch1_subject(brand, audience=None):
    """One spicy, curiosity-driven subject under 60 chars, no hyphens."""
    candidates = []
    if audience:
        candidates.append(f"{brand} is quietly all over {audience}")
    candidates += [
        f"the {brand} pattern nobody is naming",
        f"{brand} keeps showing up lately",
        f"noticed what {brand} is doing",
        "a pattern worth naming",
    ]
    for s in candidates:
        if "-" not in s and len(s) < 60:
            return s
    return "a pattern worth naming"


def _signoff():
    return "\n\nBest,\nYour name"


# Category-aware activation concept for touch 3, stated inline. Keyed by a
# lowercased category substring; falls back to a neutral on-camera moment.
def _activation_concept(category, brand, c1):
    cat = (category or "").lower()
    if "vpn" in cat or "privacy" in cat:
        return (f"{c1} hits a blackout on a match they are already watching, "
                f"opens {brand} on camera, and is back in seconds")
    if "ticket" in cat:
        return (f"{c1} scores seats to a match on {brand} live on camera and "
                f"takes the audience to the game, no script")
    if "apparel" in cat or "footwear" in cat or "merch" in cat or "kit" in cat:
        return (f"{c1} pulls on the new {brand} kit on camera in the moment it "
                f"actually matters, not a studio unboxing")
    if "gaming" in cat:
        return (f"{c1} drops into {brand} on stream and the audience plays "
                f"along in real time, not a scripted plug")
    return (f"{c1} uses {brand} on camera for something they were going to do "
            f"anyway, with zero script")


def _touch_bodies(brand, category, recent, handles, audience=None, proof_count=None):
    """The six touch bodies, each leading with something new. No hyphens,
    one CTA each. Returns a list of (body, whats_new)."""
    space = _space_word(audience, category)
    names = _creator_names(handles)
    proof_names = _join_names(names) if names else "the bigger channels here"
    c1 = names[0] if names else "the bigger channels here"

    # Touch 1 — opener (reuses the single-email body engine).
    t1 = _body(brand, category, recent, handles, audience=audience,
               proof_count=proof_count)

    # Touch 2 — one new audience insight (category neutral).
    t2 = (
        f"Hi {brand} team,\n\n"
        f"One thing I left out of my note. The audience around {space} creators "
        f"like {proof_names} is exactly the crowd most likely to act on {brand}, "
        f"the kind of intent that is hard to buy with paid media and easy to "
        f"earn with the right creator read. Want me to send the names I would "
        f"start with?"
        + _signoff()
    )
    nw2 = f"Adds an audience insight: this {space} audience is high intent for {brand}."

    # Touch 3 — a completely different frame, concept DELIVERED inline. Single
    # CTA is a soft close, not a request to send anything.
    concept = _activation_concept(category, brand, c1)
    t3 = (
        f"Hi {brand} team,\n\n"
        f"Different angle, and here is the concept rather than a tease. "
        f"{concept}. No studio, one real moment instead of a feature list. That "
        f"is the read that turns {brand} from a logo into part of the story, and "
        f"it travels across every creator in {space}. If that direction fits how "
        f"you see it, worth a quick word?"
        + _signoff()
    )
    nw3 = "States the activation concept inline, delivered not offered."

    # Touch 4 — reduce friction: routing / yes or no.
    t4 = (
        f"Hi {brand} team,\n\n"
        f"Quick one. Am I even pointed at the right desk for creator "
        f"partnerships, or is there someone better for me to talk to?"
        + _signoff()
    )
    nw4 = "Asks a routing question to reach the right owner."

    # Touch 5 — final value add: a lightweight asset.
    t5 = (
        f"Hi {brand} team,\n\n"
        f"Last useful thing from me. I wrote up the shortlist logic I would use "
        f"to pick {space} creators for {brand}: how I weigh audience intent, "
        f"conflict history, and pricing, so the choices are not a guess. It is "
        f"a short read and yours either way. Want me to drop it in your inbox?"
        + _signoff()
    )
    nw5 = "Offers a lightweight asset: the creator shortlist logic."

    # Touch 6 — the breakup: polite, easy out, no pressure.
    t6 = (
        f"Hi {brand} team,\n\n"
        f"I will close the loop here so I am not crowding your inbox. The "
        f"pattern I flagged around {brand} and {space} creators stays true "
        f"whenever the timing is right on your side. Should I close the file on "
        f"this, or is there a better person for me to pass it to?"
        + _signoff()
    )
    nw6 = "Closes the loop and offers a referral or an easy opt out."

    return [(t1, "Opens the thread leading with what the brand is already doing."),
            (t2, nw2), (t3, nw3), (t4, nw4), (t5, nw5), (t6, nw6)]


# Per-touch metadata: send timing and a human label.
_TOUCH_META = [
    ("Day 0", "Opener"),
    ("Day 3 to 4", "In thread reply"),
    ("Day 5 to 7", "In thread reply"),
    ("Day 7 to 10", "In thread reply"),
    ("Day 7 to 10 after touch 4", "In thread reply"),
    ("Day 14 to 21 from touch 1", "Breakup"),
]


def build_sequence(brand, category=None, recent=None, creators=None,
                   audience=None, proof_count=None):
    """Build and validate a full six touch follow up sequence.

    Returns {"brand", "touches": [...]} where each touch has n, day, label,
    subject, body, whats_new, word_count. Raises ValueError if any touch
    breaks a hard rule (safety net before anything is written).
    """
    brand = (brand or "").strip()
    if not brand:
        raise ValueError("A brand name is required to draft a sequence.")
    handles = creators or []

    t1_subject = _touch1_subject(brand, audience=audience)
    if "-" in t1_subject or len(t1_subject) >= 60:
        raise ValueError(f"Touch 1 subject invalid: {t1_subject!r}")
    thread_subject = f"re: {t1_subject}"
    if "-" in thread_subject:
        raise ValueError("Thread subject contains a hyphen.")

    bodies = _touch_bodies(brand, category, recent, handles, audience=audience,
                           proof_count=proof_count)
    touches = []
    for i, (body, whats_new) in enumerate(bodies, start=1):
        day, label = _TOUCH_META[i - 1]
        subject = t1_subject if i == 1 else thread_subject
        # Touch 1 must be 75 to 110 words; follow ups are short, so we only
        # cap their upper length. The opener may use a normal opener line.
        word_range = (75, 110) if i == 1 else (12, 110)
        _check_copy(body, words=word_range, allow_followup_openers=(i == 1))
        touches.append({
            "n": i, "day": day, "label": label, "subject": subject,
            "body": body, "whats_new": whats_new, "word_count": _word_count(body),
        })
    return {"brand": brand, "touches": touches}


def render_sequence_text(seq, category=None, recent=None, creators=None):
    """Render the six touch sequence to a clean, clearly-labeled document."""
    lines = []
    lines.append("=" * 64)
    lines.append(DRAFT_LABEL)
    lines.append("Six touch follow up sequence. Drafted locally. Nothing sent.")
    lines.append("=" * 64)
    lines.append("")
    lines.append(f"Brand:    {seq['brand']}")
    if category:
        lines.append(f"Category: {category}")
    if recent:
        lines.append(f"Recent placement: {recent}")
    if creators:
        lines.append(f"Example creators: {', '.join(_creator_names(creators))}")
    lines.append("")
    lines.append("Subjects: touch 1 opens the thread; touches 2 to 6 reply in thread.")
    lines.append("")
    for t in seq["touches"]:
        lines.append("-" * 64)
        lines.append(f"TOUCH {t['n']} — {t['day']} — {t['label']}")
        lines.append(f"Subject: {t['subject']}")
        lines.append(f"What is new: {t['whats_new']}")
        lines.append(f"({t['word_count']} words, one CTA)")
        lines.append("-" * 64)
        lines.append("")
        lines.append(t["body"])
        lines.append("")
    lines.append("=" * 64)
    lines.append(f"{DRAFT_LABEL}. Not sent. Review and send manually.")
    lines.append("=" * 64)
    return "\n".join(lines)


def write_sequence(seq, out_path, category=None, recent=None, creators=None):
    """Write the rendered six touch sequence to a local text file."""
    text = render_sequence_text(seq, category=category, recent=recent, creators=creators)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(text)
    return out_path
