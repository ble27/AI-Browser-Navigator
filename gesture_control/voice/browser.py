"""Parse offline voice transcripts into browser open-URL intents."""

from __future__ import annotations

import ipaddress
import re
from urllib.parse import urlparse

from gesture_control.actions import Intent, IntentType

_SITE_ALIASES: dict[str, str] = {
    "amazon": "https://www.amazon.com",
    "apple": "https://www.apple.com",
    "bing": "https://www.bing.com",
    "chat gpt": "https://chatgpt.com",
    "chatgpt": "https://chatgpt.com",
    "claude": "https://claude.ai",
    "claude ai": "https://claude.ai",
    "cursor": "https://cursor.com",
    "facebook": "https://www.facebook.com",
    "github": "https://github.com",
    "google": "https://www.google.com",
    "linkedin": "https://www.linkedin.com",
    "netflix": "https://www.netflix.com",
    "openai": "https://openai.com",
    "perplexity": "https://www.perplexity.ai",
    "reddit": "https://www.reddit.com",
    "twitter": "https://x.com",
    "wikipedia": "https://www.wikipedia.org",
    "x": "https://x.com",
    "youtube": "https://www.youtube.com",
}

_TRAILING_SITE_WORDS = frozenset({"webpage", "website", "site"})
_COMMAND_PREFIXES = (
    "browse to ",
    "go to ",
    "open ",
    "pull up ",
    "take me to ",
    "visit ",
)
_HOST_LABEL = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$", re.IGNORECASE)
_LOCAL_SUFFIXES = (".internal", ".local", ".localhost")


def parse_browser_command(transcript: str) -> Intent | None:
    """Parse an ``open`` voice command into an ``OPEN_URL`` intent.

    Accepts ``open``, ``go to``, or ``visit`` followed by an allowlisted site,
    a public bare domain, or an explicit HTTPS URL. Matching aliases is
    case-insensitive. Unknown words and unsafe hosts/schemes return ``None``.

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

    folded = collapsed.casefold()
    prefix = next((item for item in _COMMAND_PREFIXES if folded.startswith(item)), None)
    if prefix is None:
        return None

    candidate = collapsed[len(prefix) :].strip()
    if candidate.casefold().startswith("the "):
        candidate = candidate[4:].strip()
    if not candidate:
        return None

    candidate_folded = candidate.casefold()
    if candidate_folded.startswith("https://"):
        return _intent_for_https_url(candidate)

    # A colon or explicit scheme is never interpreted as an alias/bare domain.
    if "://" in candidate_folded or ":" in candidate_folded:
        return None

    # Whisper commonly appends sentence punctuation to a spoken site alias.
    # Strip only for alias matching; URL validation above keeps URL syntax intact.
    site_tokens = candidate.rstrip(".,!?").split()
    if site_tokens and site_tokens[-1].casefold() in _TRAILING_SITE_WORDS:
        site_tokens = site_tokens[:-1]
    if not site_tokens:
        return None
    if site_tokens[-1].casefold() == "app":
        return None

    alias_url = _match_site_alias(site_tokens)
    if alias_url is not None:
        return Intent(IntentType.OPEN_URL, url=alias_url)

    if len(site_tokens) != 1:
        return None

    bare_domain = candidate.rstrip(".,!?")
    if any(character.isspace() for character in bare_domain):
        return None
    return _intent_for_https_url(f"https://{bare_domain}")


def _match_site_alias(tokens: list[str]) -> str | None:
    """Return the longest allowlisted alias URL for ``tokens``."""
    for length in range(len(tokens), 0, -1):
        key = " ".join(tokens[:length]).casefold()
        url = _SITE_ALIASES.get(key)
        if url is not None:
            return url
    return None


def _intent_for_https_url(url: str) -> Intent | None:
    """Return an OPEN_URL intent when ``url`` is a valid https absolute URL.

    Args:
        url: Candidate URL string with original casing preserved.

    Returns:
        An ``Intent`` carrying ``url`` unchanged when it has an https scheme
        and a network location; otherwise ``None``.
    """
    if any(character.isspace() for character in url) or "\\" in url:
        return None
    parsed = urlparse(url)
    if parsed.scheme.casefold() != "https" or not parsed.netloc:
        return None
    # Reject embedded credentials so open-URL never carries userinfo.
    if parsed.username is not None or parsed.password is not None:
        return None
    try:
        parsed_port = parsed.port
    except ValueError:
        return None
    if parsed_port is not None and not 1 <= parsed_port <= 65_535:
        return None
    hostname = parsed.hostname
    if hostname is None or not _is_public_domain(hostname):
        return None
    return Intent(IntentType.OPEN_URL, url=url)


def _is_public_domain(hostname: str) -> bool:
    """Return whether a hostname is a syntactically valid public domain.

    Args:
        hostname: Parsed hostname without credentials or port.

    Returns:
        ``True`` for dotted DNS names with valid labels and a non-numeric TLD.
        Localhost names, IP literals, and local/private suffixes return
        ``False``.
    """
    host = hostname.rstrip(".").casefold()
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        return False

    if host == "localhost" or host.endswith(_LOCAL_SUFFIXES):
        return False
    labels = host.split(".")
    if len(labels) < 2 or any(not _HOST_LABEL.fullmatch(label) for label in labels):
        return False
    top_level = labels[-1]
    return (
        len(top_level) >= 2
        and not top_level.isdigit()
        and (top_level.isalpha() or top_level.startswith("xn--"))
    )
