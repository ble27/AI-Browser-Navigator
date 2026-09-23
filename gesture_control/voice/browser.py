"""Parse offline voice transcripts into browser open-URL intents."""

from __future__ import annotations

from urllib.parse import urlparse

from gesture_control.actions import Intent, IntentType

_SITE_ALIASES: dict[str, str] = {
    "cursor": "https://cursor.com",
    "apple": "https://www.apple.com",
}

_TRAILING_SITE_WORDS = frozenset({"webpage", "website", "site"})


def parse_browser_command(transcript: str) -> Intent | None:
    """Parse an ``open`` voice command into an ``OPEN_URL`` intent.

    Accepts case-insensitive transcripts of the form ``open`` + optional
    ``the`` + either an https URL with a network location, or an allowlisted
    site name (optionally followed by ``webpage`` / ``website`` / ``site``).
    Unknown names and non-https schemes return ``None``.

    Args:
        transcript: Raw voice transcript text to parse.

    Returns:
        An ``Intent`` with ``IntentType.OPEN_URL`` and a concrete https
        ``url``, or ``None`` when the transcript is not a recognized open
        command.
    """
    collapsed = " ".join(transcript.split())
    if not collapsed:
        return None

    tokens = collapsed.split()
    if tokens[0].strip(".,!?").casefold() != "open":
        return None

    rest = tokens[1:]
    if not rest:
        return None

    if rest[0].casefold() == "the":
        rest = rest[1:]
    if not rest:
        return None

    candidate = " ".join(rest)
    candidate_folded = candidate.casefold()
    if candidate_folded.startswith("https://"):
        return _intent_for_https_url(candidate)

    # Reject other absolute schemes before treating the remainder as a site alias.
    if "://" in candidate_folded or candidate_folded.startswith("javascript:"):
        return None

    # Whisper commonly appends sentence punctuation to a spoken site alias.
    # Strip only for alias matching; URL validation above keeps URL syntax intact.
    site_tokens = candidate.rstrip(".,!?").split()
    if site_tokens and site_tokens[-1].casefold() in _TRAILING_SITE_WORDS:
        site_tokens = site_tokens[:-1]
    if len(site_tokens) != 1:
        return None

    url = _SITE_ALIASES.get(site_tokens[0].casefold())
    if url is None:
        return None
    return Intent(IntentType.OPEN_URL, url=url)


def _intent_for_https_url(url: str) -> Intent | None:
    """Return an OPEN_URL intent when ``url`` is a valid https absolute URL.

    Args:
        url: Candidate URL string with original casing preserved.

    Returns:
        An ``Intent`` carrying ``url`` unchanged when it has an https scheme
        and a network location; otherwise ``None``.
    """
    parsed = urlparse(url)
    if parsed.scheme.casefold() != "https" or not parsed.netloc:
        return None
    # Reject embedded credentials so open-URL never carries userinfo.
    if parsed.username is not None or parsed.password is not None:
        return None
    return Intent(IntentType.OPEN_URL, url=url)
