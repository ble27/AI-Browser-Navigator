"""Context-gated repair of known brand mishears in STT text.

Applied to every streaming transcript event before clause segmentation so
parsers never see raw brand confusions such as ``cloud`` for ``claude``.

Repair order under a target verb:
1. Exact miss table (measured spike floor).
2. Closed-vocabulary fuzzy match (phonetic skeleton + edit ratio).
"""

from __future__ import annotations

from difflib import SequenceMatcher

# Longest multi-word verbs first so "browse to" wins over a bare "to".
_TARGET_VERBS: tuple[str, ...] = (
    "take me to ",
    "browse to ",
    "pull up ",
    "go to ",
    "visit ",
    "query ",
    "asked ",
    "ask ",
    "opened ",
    "open ",
)

# Exact floor from S0/S0b measured misses, plus a short curated sibling list
# for live confusions that stay ambiguous under pure edit-distance margins
# (e.g. color≈cursor). Prefer fuzzy for novel misses; do not grow this table
# from every live session.
_BRAND_MISSES: tuple[tuple[str, str], ...] = (
    ("up an a", "openai"),
    ("open a i", "openai"),
    ("open ai", "openai"),
    ("openopene", "openai"),
    ("chat gpt", "chatgpt"),
    ("chatibiti", "chatgpt"),
    ("chatibity", "chatgpt"),
    ("chattibiti", "chatgpt"),
    ("a i", "openai"),
    ("clawed", "claude"),
    ("cloud", "claude"),
    ("clod", "claude"),
    ("claud", "claude"),
    ("color", "claude"),
    ("ai", "openai"),
)

# Whole-line glued forms with no separable verb+target (medium_streaming miss).
_GLUED_LINE_MISSES: tuple[tuple[str, str], ...] = (("openopene", "open openai"),)

# Closed brand / site / assistant tokens the fuzzy matcher may rewrite to.
_CLOSED_BRANDS: tuple[str, ...] = (
    "amazon",
    "apple",
    "bing",
    "chatgpt",
    "claude",
    "cursor",
    "facebook",
    "gemini",
    "github",
    "google",
    "linkedin",
    "netflix",
    "openai",
    "perplexity",
    "reddit",
    "twitter",
    "wikipedia",
    "youtube",
)

_FUZZY_MIN_SCORE = 0.65
_FUZZY_HIGH_SCORE = 0.72
_FUZZY_MARGIN = 0.15


def _alnum(text: str) -> str:
    return "".join(ch for ch in text.casefold() if ch.isalnum())


def _skeleton(text: str) -> str:
    """Consonant skeleton: drop vowels after the first character."""
    compact = _alnum(text)
    if not compact:
        return ""
    out: list[str] = []
    prev = ""
    for index, char in enumerate(compact):
        if char in "aeiou":
            if index == 0:
                out.append(char)
                prev = char
            continue
        if char != prev:
            out.append(char)
            prev = char
    return "".join(out)


def _pair_score(heard: str, candidate: str) -> float:
    heard_n = _alnum(heard)
    cand_n = _alnum(candidate)
    if not heard_n or not cand_n:
        return 0.0
    ratio = SequenceMatcher(None, heard_n, cand_n).ratio()
    heard_s = _skeleton(heard)
    cand_s = _skeleton(candidate)
    skeleton_ratio = SequenceMatcher(None, heard_s, cand_s).ratio() if heard_s and cand_s else 0.0
    exact_skeleton = 1.0 if heard_s == cand_s and len(heard_s) >= 3 else 0.0
    return max(ratio, skeleton_ratio, exact_skeleton)


def _fuzzy_brand(token: str) -> str | None:
    """Return the best closed brand for ``token``, or None if ambiguous/weak."""
    folded = token.casefold().strip(".,!?;:")
    if not folded:
        return None
    if folded in _CLOSED_BRANDS:
        return folded
    ranked = sorted(
        ((_pair_score(folded, brand), brand) for brand in _CLOSED_BRANDS),
        reverse=True,
    )
    best_score, best = ranked[0]
    second = ranked[1][0] if len(ranked) > 1 else 0.0
    if best_score >= _FUZZY_HIGH_SCORE and (best_score - second) >= 0.08:
        return best
    if best_score >= _FUZZY_MIN_SCORE and (best_score - second) >= _FUZZY_MARGIN:
        return best
    return None


def _fuzzy_repair_remainder(remainder: str) -> str | None:
    """Try to rewrite a leading brand span inside ``remainder``.

    Stops before clause delimiters (``and`` / ``then``) so compound commands
    like ``open amazon and click orders`` keep their split points.
    """
    words = remainder.split()
    if not words:
        return None
    candidate: list[str] = []
    for word in words:
        token = word.casefold().strip(".,!?;:")
        if token in {"and", "then"}:
            break
        candidate.append(word)
    if not candidate:
        return None
    # Prefer longer spans first so "chat gpt" can fuzzy to chatgpt.
    for width in range(min(3, len(candidate)), 0, -1):
        span = " ".join(candidate[:width])
        brand = _fuzzy_brand(span)
        if brand is None:
            continue
        # No-op when the span is already the canonical brand token(s).
        if span.casefold().replace(" ", "") == brand.casefold():
            return None
        if span.casefold() == brand.casefold():
            return None
        tail = " ".join(words[width:])
        return brand if not tail else f"{brand} {tail}"
    return None


def repair_command_text(text: str) -> str:
    """Normalize one STT line and repair known brand mishears.

    Collapses whitespace, turns hyphens into spaces, strips trailing sentence
    punctuation, normalizes past-tense open/ask verbs, applies the exact
    phonetic-miss table, then closed-vocab fuzzy matching — only when the
    target sits directly after a target verb (open, ask, query, go to, visit,
    browse to, take me to, pull up), so literal text such as
    ``type cloud storage`` is never rewritten.

    Args:
        text: Raw STT line, possibly empty.

    Returns:
        Normalized text with at most one brand repair applied after a target
        verb, or an empty string when ``text`` is blank.
    """
    collapsed = " ".join(text.replace("-", " ").split())
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
        if verb in {"opened ", "asked "}:
            verb_out = {"opened ": "open ", "asked ": "ask "}[verb]
        else:
            verb_out = collapsed[: len(verb)]
        for miss, brand in _BRAND_MISSES:
            if rem_folded == miss:
                return verb_out + brand
            miss_prefix = miss + " "
            if rem_folded.startswith(miss_prefix):
                return verb_out + brand + remainder[len(miss) :]
        fuzzy = _fuzzy_repair_remainder(remainder)
        if fuzzy is not None:
            return verb_out + fuzzy
        if verb_out != collapsed[: len(verb)]:
            return verb_out + remainder
        return collapsed

    return collapsed
