# Research: Voice “open named website in Google Chrome”

**Date:** 2026-09-22  
**Repo:** AI-Gestures-Tool  
**Scope:** Local-first, offline Python voice commands that open a named site in
Google Chrome (macOS first; cross-platform via `InputBackend`). In-page control
of a web app is explicitly out of scope.

---

## Question

What is a sound, local-first way for this tool to open a named website in
**Google Chrome specifically** from a spoken phrase such as “Open cursor
webpage” or “Open Apple website”, without a Chrome extension that drives page
DOM?

---

## Findings

### 1. OS-level URL open vs Python `webbrowser` — who picks the browser?

#### macOS `open`

The system `open(1)` man page states that `open` opens a file, directory, or
URL as if double-clicked; if no application is specified, Launch Services picks
the default handler. With `-a application`, the caller **specifies** the app:

- `-a application` — “Specifies the application to use for opening the file”
- Example: `open http://www.apple.com/` opens the URL in the **default** browser
- Example pattern: `open -a /Applications/TextEdit.app '…'` opens in a named app

**Source:** local `man open` (OPEN(1)); same semantics documented in the synopsis
(`/usr/bin/open`).

**Guarantee for Chrome:**  
`open -a "Google Chrome" "https://example.com"` targets Google Chrome by name.
Without `-a` / `-b`, Chrome is **not** guaranteed.

Bundle-id alternative also exists (`-b bundle_identifier`), which can pin
`com.google.Chrome` without relying on display name — useful if localization
renames the app bundle display string. Prefer whichever the macOS adapter finds
installed.

#### Windows `start`

Microsoft’s `start` command docs:

- Non-executable files (including URLs) open via file association — URLs open in
  the **default** browser.
- Example: `start "Bing" "https://www.bing.com"` → default browser.
- To run a specific program: `start <"title"> … <program> [<parameter>…]`.

**Source:**  
https://learn.microsoft.com/en-us/windows-server/administration/windows-commands/start

**Guarantee for Chrome:**  
`start "" "C:\Path\To\chrome.exe" "https://example.com"` (or a `chrome` /
`chrome.exe` on `PATH`) targets Chrome. Bare `start https://…` does **not**.

#### Linux: `google-chrome` / `xdg-open`

Chromium’s Linux man page synopsis:

```text
google-chrome [OPTION] [PATH|URL]
```

Passing a URL as an argument is a supported launch form; repeated invocations
reuse an existing process for a given user-data directory.

**Source:**  
https://chromium.googlesource.com/chromium/reference_builds/chrome_linux/+/b0e34e9feec75def246f0eb0f1b71f2c7406bd1a/chrome.1

Freedesktop `xdg-open`:

- Opens a URL in the user’s **preferred** web browser.
- Supports `http` / `https` (among others).

**Source:**  
https://portland.freedesktop.org/doc/xdg-open.html

**Guarantee for Chrome:**  
`google-chrome https://example.com` (or `chromium` / distro binary) targets
Chrome/Chromium. `xdg-open https://…` follows the desktop default and does
**not** guarantee Chrome.

Chromium also documents CLI switches such as `--new-window` (“Launches URL in
new browser window”) in source:

**Source:**  
https://chromium.googlesource.com/chromium/src/+/main/chrome/common/chrome_switches.cc

#### Python `webbrowser`

Official stdlib docs:

- `webbrowser.open(url)` — “Display *url* using the **default** browser.”
- Controllers exist for named types including `'chrome'`, `'google-chrome'`,
  `'chromium'`, and on macOS `'macosx'` / `'safari'`.
- `BROWSER` env var can reorder / override preferred browsers.
- Docs note that on macOS the platform defaults “do not refer to command-line
  tools on `PATH`” (3.14 change commentary).

**Source:**  
https://docs.python.org/3/library/webbrowser.html

CPython’s macOS registration (stdlib implementation, inspectable locally)
registers:

- `"chrome"` → `MacOSXOSAScript('google chrome')` (AppleScript `tell application
  "google chrome"` / `open location`)
- `"MacOSX"` → default browser via Launch Services / `open location`

So `webbrowser.get("chrome").open(url)` **can** target Chrome on macOS when that
registration succeeds, but:

1. It is still an OS/AppleScript launch path owned by the stdlib, not by this
   repo’s `InputBackend` seam.
2. On Windows/Linux, Chrome registration depends on finding a `chrome` /
   `google-chrome` executable on `PATH` (see same `register_standard_browsers`
   logic); failure modes differ by platform.
3. `webbrowser.open()` alone never promises Chrome.

**Summary table**

| Mechanism | Guarantees Google Chrome? |
| --- | --- |
| macOS `open https://…` | No (default browser) |
| macOS `open -a "Google Chrome" https://…` | Yes (named app) |
| Windows `start https://…` | No (default browser) |
| Windows `start "" chrome.exe https://…` | Yes (named program) |
| Linux `xdg-open https://…` | No (preferred browser) |
| Linux `google-chrome https://…` | Yes (Chrome binary) |
| `webbrowser.open(url)` | No (default) |
| `webbrowser.get("chrome").open(url)` | Often yes if Chrome is registered; platform-dependent |

---

### 2. Native Messaging, CDP, extension — required to open a URL?

#### Chrome Native Messaging

Official Chrome docs: Native Messaging lets **extensions** exchange messages
with a native host over stdio after registering a host manifest and
`allowed_origins`. It is an extension ↔ native-app bridge, not a general “open
this URL” API for arbitrary desktop apps.

**Source:**  
https://developer.chrome.com/docs/extensions/develop/concepts/native-messaging

**Conclusion:** Not required (and not appropriate as the primary path) for
“open https://… in Chrome.”

#### Chrome DevTools Protocol (CDP)

The Target domain’s `createTarget` command “Creates a new page” with an initial
`url` parameter — i.e. CDP *can* open a tab, but only after attaching to a
debuggable Chrome instance.

**Source (protocol definition):**  
https://raw.githubusercontent.com/ChromeDevTools/devtools-protocol/master/pdl/domains/Target.pdl  
(`command createTarget`, parameter `string url`)

Chrome’s own security guidance (Chrome 136+): `--remote-debugging-port` /
`--remote-debugging-pipe` are no longer respected for the **default** user data
directory; a non-standard `--user-data-dir` is required. That is hostile to
driving the user’s everyday Chrome profile for a simple “open site” command.

**Source:**  
https://developer.chrome.com/blog/remote-debugging-port

**Conclusion:** CDP is overkill and operationally wrong for this milestone
(debug ports, separate profiles, automation threat model). Reserve for later
automation / in-page work if ever justified.

#### Extension APIs / content scripts

`chrome.tabs.create` creates a new tab (extension context). Content scripts run
in page context for DOM access.

**Sources:**  
https://developer.chrome.com/docs/extensions/reference/api/tabs  
https://developer.chrome.com/docs/extensions/mv3/content_scripts/

**Conclusion:**

| Goal | Sufficient mechanism |
| --- | --- |
| Open a URL as a new Chrome tab/window | OS launch of Chrome with a URL (`open -a`, `chrome.exe`, `google-chrome`) |
| In-page control / DOM / app automation | Extension (tabs + scripting/content scripts) and/or CDP — **out of scope** |

No extension, Native Messaging host, or CDP session is required to open a tab.

---

### 3. Safe resolution of spoken site names → `https` URLs

Spoken aliases (“cursor”, “apple”) are **not** URLs. Free-form “guess a domain
from speech” invites:

- Homograph / lookalike domains (Unicode confusables; IDNA ACE forms).
- Accidental `javascript:`, `file:`, or other schemes if raw STT text is passed
  through.
- `urljoin` footguns when combining attacker-controlled fragments with a base.

Python `urllib.parse` docs explicitly warn:

- APIs “do not perform validation of inputs.”
- Callers with security implications should verify `scheme`, `path`, `hostname`.
- Characters that affect `netloc` under NFKC normalization can raise
  `ValueError` (related to IDNA/confusable parsing).
- `urljoin` with attacker-controlled absolute URLs is unsafe.

**Source:**  
https://docs.python.org/3/library/urllib.parse.html

IDNA conversion (Unicode ↔ ACE) is documented in `encodings.idna`; it is for
encoding correctness, not phishing prevention.

**Source:**  
https://docs.python.org/3/library/codecs.html#module-encodings.idna

**Recommended policy for this product (local-first, offline):**

1. **Allowlist alias table** (small, built-in, expandable via config later):
   - `cursor` → `https://cursor.com`
   - `apple` → `https://www.apple.com`
   - Normalize spoken tokens (lowercase, strip “webpage” / “website” / “site”).
2. **Explicit https URL** only if STT yields a string that parses as
   `scheme == "https"`, nonempty hostname, no credentials in netloc, and
   preferably ASCII/punycode hostname after IDNA — reject `http:`, `file:`,
   `javascript:`, relative URLs, and bare host guesses.
3. **Do not** invent domains from free speech (“open my bank”) without an
   allowlist hit.
4. Optional later: user YAML allowlist in config (fits existing config story in
   PRD); still no open-ended DNS guessing in v1.

This matches the PRD’s “deterministic command grammar first” voice design and
the backlog’s deferral of free-form LLM phrasing.

**Sources (repo):**  
`docs/PRD.md` §7.3 Voice agent; `docs/BACKLOG.md` (optional Ollama free-form).

---

### 4. How this lands on existing `Intent` + `InputBackend` contracts

#### Repo contracts (current tree)

**Voice package is not implemented yet** — only a package docstring stub:

```1:7:gesture_control/voice/__init__.py
"""Offline voice command pipeline.

Wake word (``openWakeWord``) -> offline speech-to-text (``faster-whisper``)
-> deterministic intent parser -> offline text-to-speech (``Piper``) for
confirmations. All dependencies in this package are optional and lazily
imported, so a gesture-only install never requires audio libraries.
"""
```

**Action Mapper / Intent** (today: cursor move + left click only):

```11:30:gesture_control/actions/mapper.py
class IntentType(StrEnum):
    """Actions currently understood by the M2 Action Mapper."""

    MOVE_CURSOR = "move_cursor"
    CLICK_LEFT = "click_left"


@dataclass(frozen=True, slots=True)
class Intent:
    """A modality-neutral user action.

    Attributes:
        kind: The action requested by a gesture or voice command.
        x: Target cursor horizontal coordinate, required for ``MOVE_CURSOR``.
        y: Target cursor vertical coordinate, required for ``MOVE_CURSOR``.
    """

    kind: IntentType
    x: int | None = None
    y: int | None = None
```

**InputBackend** (today: `screen_size`, `move_to`, `click_left` only) — quoted
contract from `gesture_control/backends/base.py`:

- Abstract methods: `screen_size()`, `move_to(x, y)`, `click_left()`
- Docstring: “The sole interface through which actions inject OS input.”
- Every concrete method must honor `safe_pause` before acting.

**Wiring rules (non-negotiable):**

- Gestures and voice produce `Intent`; only the Action Mapper calls
  `InputBackend`. Never call OS APIs from `voice/` or `gestures/`.
- **Sources:** `AGENTS.md` (“The core contracts”, “How to add a new voice
  command”); `gesture_control/actions/__init__.py`; `docs/PRD.md` architecture
  diagram (STT → Intent Parser → Mapper → Backend).

PRD already sketches a richer backend surface (`move_to`, `click`, `scroll`,
`key`, `switch_app`, …) but those methods are **not** on the live ABC yet —
`open_url` / Chrome-specific open is the same kind of gap.

**Sources:** `docs/PRD.md` §6 Architecture; `gesture_control/backends/base.py`.

#### Recommended contract shape (design only — not implemented here)

| Layer | Responsibility |
| --- | --- |
| `voice/` parser | Phrase → `Intent(IntentType.OPEN_URL, url="https://…")` after alias / https validation. No `subprocess`, no `open`, no `webbrowser`. |
| `actions.ActionMapper` | `OPEN_URL` → `backend.open_url(intent.url)` (or `open_in_browser`). |
| `backends.InputBackend` | New abstract `open_url(url: str) -> None` gated by `safe_pause`. |
| `backends.macos.MacOSInputBackend` | `subprocess.run(["open", "-a", "Google Chrome", url], …)` (or `-b com.google.Chrome`). |
| Future Windows/Linux adapters | `chrome.exe` / `google-chrome` with URL arg; fail loudly if Chrome missing. |

Whether `open_url` is named `open_url` (browser preference in config) or
`open_in_chrome` (hard Chrome requirement of this feature): prefer
**`open_url` + adapter policy “always Google Chrome for this product feature”**
so the Intent stays modality-neutral while the macOS/Windows/Linux adapters
implement the Chrome pin. Document the pin in the adapter docstring.

Safe-pause: treat URL open as a privileged session action and **gate it** the
same way as mouse injection (`AGENTS.md` safety invariant; backend already
checks `safe_pause` before `move_to` / `click_left`).

---

### 5. Recommended vertical slice for **this** milestone only

Ship a thin path that proves grammar → Intent → mapper → backend open, with
hardware-free unit tests. Aligns with voice milestone M5 in `docs/PRD.md` but
can land as a small `feat:` ahead of full wake-word/STT if desired.

#### Phrase grammar (deterministic)

- `open <alias> [webpage|website|site]?`
- `open <https-url>` where STT text matches a validated `https://…` form

Examples: “open cursor webpage”, “open apple website”, “open https://cursor.com”.

Reject: “open bank”, “open http://…”, bare “cursor.com” without allowlist or
`https://` prefix (until explicitly productized).

#### Intent shape

```text
IntentType.OPEN_URL
Intent(kind=OPEN_URL, url: str)   # url always absolute https after resolution
```

(`x`/`y` remain unused; keep dataclass additive fields rather than inventing a
parallel DTO.)

#### Backend method

```text
InputBackend.open_url(url: str) -> None
```

macOS first implementation: `open -a "Google Chrome" <url>` via `subprocess`
(not `webbrowser.open`, so Chrome is guaranteed and the call lives behind the
OS seam).

#### Unit-test seams (no Chrome required)

1. Alias table: `"cursor"` / `"apple webpage"` → exact https URLs.
2. Parser: phrase fixtures → `Intent(OPEN_URL, url=…)`; reject cases.
3. URL guard: non-https schemes / empty host / credentials rejected.
4. ActionMapper: `OPEN_URL` calls mock backend `open_url` once with that URL;
   skipped when `safe_pause` is asserted at backend (test backend records calls).
5. Optional: macOS adapter unit test with `subprocess` patched — assert argv
   `["open", "-a", "Google Chrome", "https://…"]`.

#### Docs / process (when implementing)

Per `AGENTS.md`: QA checklist entry, README cheat-sheet line, backlog update for
deferred in-page work, same commit as code.

---

## Recommendation

**Use OS-level “open this URL with Google Chrome” behind `InputBackend.open_url`,
fed by an allowlisted (plus explicit-https) voice Intent. Do not use Native
Messaging, CDP, or an extension for this milestone.**

Concrete preference:

1. Resolve speech → `https` URL in pure Python (alias table + strict https
   parse).
2. Emit `Intent(OPEN_URL, url=…)`.
3. Mapper dispatches to `backend.open_url`.
4. macOS adapter: `open -a "Google Chrome" <url>` (or `-b com.google.Chrome`).
5. Later adapters: Windows `chrome.exe` + URL; Linux `google-chrome` /
   `chromium` + URL — never rely on default-browser helpers (`webbrowser.open`,
   bare `xdg-open`, bare `start https://…`) when the product requirement is
   Chrome-specific.

`webbrowser` remains a useful *reference* for controller registration quirks,
but the product seam should own the Chrome pin inside adapters for predictability
and testability.

---

## Deferred scope (backlog candidates)

Track in `docs/BACKLOG.md` when implementing (do not leave inline TODOs):

- In-page / web-app control (DOM, form fill, click-in-page) via Chrome
  extension, Native Messaging, and/or CDP — explicitly later milestone.
- Driving the user’s default browser instead of Chrome (product decision).
- Free-form site discovery / search (“open my email”) without allowlist
  (overlaps optional Ollama backlog item).
- Focusing an existing tab by URL (`--focus=…` Chromium switch) vs always
  opening a new tab — evaluate after basic open works.
- User-editable YAML site allowlist in config profiles.

---

## Sources index

| Claim area | Primary source |
| --- | --- |
| macOS `open -a` / default URL handler | `man open` (OPEN(1)) |
| Windows `start` + URL = default browser | https://learn.microsoft.com/en-us/windows-server/administration/windows-commands/start |
| Linux preferred browser | https://portland.freedesktop.org/doc/xdg-open.html |
| Chrome accepts URL on CLI | https://chromium.googlesource.com/chromium/reference_builds/chrome_linux/+/b0e34e9feec75def246f0eb0f1b71f2c7406bd1a/chrome.1 |
| Chromium CLI switches (`--new-window`, etc.) | https://chromium.googlesource.com/chromium/src/+/main/chrome/common/chrome_switches.cc |
| Python default vs named browsers | https://docs.python.org/3/library/webbrowser.html |
| Native Messaging purpose | https://developer.chrome.com/docs/extensions/develop/concepts/native-messaging |
| CDP `Target.createTarget` | https://raw.githubusercontent.com/ChromeDevTools/devtools-protocol/master/pdl/domains/Target.pdl |
| Remote debugging / profile constraints | https://developer.chrome.com/blog/remote-debugging-port |
| Extension `tabs.create` | https://developer.chrome.com/docs/extensions/reference/api/tabs |
| URL parse / validation caveats | https://docs.python.org/3/library/urllib.parse.html |
| IDNA | https://docs.python.org/3/library/codecs.html#module-encodings.idna |
| Repo Intent / backend / voice rules | `AGENTS.md`, `gesture_control/actions/mapper.py`, `gesture_control/backends/base.py`, `gesture_control/voice/__init__.py`, `docs/PRD.md`, `docs/BACKLOG.md` |
