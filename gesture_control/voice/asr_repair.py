"""Context-gated repair of known brand mishears in STT text.

Applied to every streaming transcript event before clause segmentation so
parsers never see raw brand confusions such as ``cloud`` for ``claude``.
"""

from __future__ import annotations

# Longest multi-word verbs first so "browse to" wins over a bare "to".
_TARGET_VERBS: tuple[str, ...] = (
    "take me to ",
    "browse to ",
    "pull up ",
    "go to ",
    "visit ",
    "query ",
    "ask ",
    "open ",
)

# Longest miss phrases first. Entries come only from measured spike misses in
# docs/research/voice-streaming-stt.md (plus close phonetic siblings listed in
# the S0b plan).
_BRAND_MISSES: tuple[tuple[str, str], ...] = (
    ("up an a", "openai"),
    ("open a i", "openai"),
    ("open ai", "openai"),
    ("openopene", "openai"),
    ("chat gpt", "chatgpt"),
    ("a i", "openai"),
    ("cloud", "claude"),
    ("clod", "claude"),
    ("claud", "claude"),
    ("ai", "openai"),
)

# Whole-line glued forms with no separable verb+target (medium_streaming miss).
_GLUED_LINE_MISSES: tuple[tuple[str, str], ...] = (("openopene", "open openai"),)


def repair_command_text(text: str) -> str:
    """Normalize one STT line and repair known brand mishears.

    Collapses whitespace, strips trailing sentence punctuation, and rewrites a
    fixed phonetic-miss table only when it directly follows a target verb
    (open, ask, query, go to, visit, browse to, take me to, pull up), so
    literal text such as "type cloud storage" is never rewritten.

    Args:
        text: Raw STT line, possibly empty.

    Returns:
        Normalized text with at most one brand repair applied after a target
        verb, or an empty string when ``text`` is blank.
    """
    collapsed = " ".join(text.split())
    if not collapsed:
        return ""
    collapsed = collapsed.rstrip(".,!?;:")
    if not collapsed:
        return ""

    folded = collapsed.casefold()
    for miss, replacement in _GLUED_LINE_MISSES:
        if folded == miss:
            return replacement
        prefix = miss + " "
        if folded.startswith(prefix):
            return replacement + collapsed[len(miss) :]

    for verb in _TARGET_VERBS:
        if not folded.startswith(verb):
            continue
        remainder = collapsed[len(verb) :]
        rem_folded = remainder.casefold()
        for miss, brand in _BRAND_MISSES:
            if rem_folded == miss:
                return collapsed[: len(verb)] + brand
            miss_prefix = miss + " "
            if rem_folded.startswith(miss_prefix):
                return collapsed[: len(verb)] + brand + remainder[len(miss) :]
        return collapsed

    return collapsed
