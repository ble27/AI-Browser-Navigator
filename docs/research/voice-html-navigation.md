# Research: Voice in-page control of an already-open Chrome tab

**Date:** 2026-09-22  
**Repo:** AI-Gestures-Tool  
**Scope:** Local-first, offline Python voice tool on macOS that already opens
sites with `open -a "Google Chrome" <https url>`. Next milestone: spoken
commands such as “click on log in” then “type hello” acting on the page the
user already has open. Owner’s own Chrome session only — not malware, not
credential theft, not driving someone else’s browser.

**Related prior note:** `docs/research/voice-open-in-chrome.md` (worktree /
voice-chrome branch) concluded OS-level open is enough to *open* a URL, and
deferred in-page DOM control to a later milestone.

---

## Question

How can a spoken command act on the HTML/accessibility surface of a page
already open in the user’s Google Chrome, and which mechanisms are feasible
against primary sources?

---

## 1. Can a normal Python process read the HTML of the user’s already-open Chrome profile with **no extension** and **no debug port**?

### Conclusion: **No.**

Primary sources that define how in-page DOM access actually works all require
one of: an **extension** (content script / `chrome.scripting`), a **Native
Messaging** bridge to that extension, or a **Chrome DevTools Protocol**
session (remote debugging). None of those are “plain Python attached to the
default running Chrome.”

| Claim | Source |
| --- | --- |
| Page DOM is read/changed by **content scripts** that run in the page context as part of an **extension** | https://developer.chrome.com/docs/extensions/develop/concepts/content-scripts (“Content scripts are files that run in the context of web pages… able to read details of the web pages… using the standard Document Object Model”) |
| Programmatic injection into a tab requires the extension `scripting` API + host/`activeTab` permissions | https://developer.chrome.com/docs/extensions/reference/api/scripting |
| Native Messaging is an **extension ↔ native host** stdio bridge, not a general API for arbitrary desktop apps to scrape Chrome | https://developer.chrome.com/docs/extensions/develop/concepts/native-messaging (“Extensions can exchange messages with native applications…”) |
| CDP DOM/Accessibility commands exist only for an attached DevTools/debug target | https://chromedevtools.github.io/devtools-protocol/tot/DOM/ ; Accessibility PDL https://raw.githubusercontent.com/ChromeDevTools/devtools-protocol/master/pdl/domains/Accessibility.pdl |
| From Chrome 136, `--remote-debugging-port` / `--remote-debugging-pipe` are **not** respected for the **default** user data directory; a non-standard `--user-data-dir` is required | https://developer.chrome.com/blog/remote-debugging-port |

macOS Accessibility (`AXUIElement` / `NSAccessibility`) can expose an
**accessibility hierarchy** (roles, titles/labels, actions such as press) for
running apps — that is **not** raw HTML of the document, and it is a separate
OS API requiring Accessibility permission, not “read Chrome’s HTML from disk.”

**Sources:**  
https://developer.apple.com/library/archive/documentation/Accessibility/Conceptual/AccessibilityMacOSX/OSXAXmodel.html  
https://developer.apple.com/documentation/applicationservices/axuielement  
https://developer.apple.com/documentation/appkit/nsaccessibility  

`open -a "Google Chrome" <url>` only launches/activates Chrome with a URL; it
does not grant the calling process DOM access
(`docs/research/voice-open-in-chrome.md`; macOS `man open`).

The on-disk Chrome profile stores cookies, history, etc.; it is **not** a live
serialized DOM of the front tab. Live markup requires a page-context channel
(extension/CDP) or an OS accessibility view (AX), not a Python file open of
`~/Library/Application Support/Google/Chrome/…`.

---

## 2. Three real mechanisms compared

### (a) Chrome extension content script + Native Messaging

**What it is**

1. A MV3 extension injects a content script (static/`all_frames`, dynamic
   `scripting.registerContentScripts`, or `scripting.executeScript`).
2. The script walks interactive elements (buttons, links, inputs) and builds
   descriptors from `role` / `aria-label` / labelled-by text / `innerText` /
   placeholder — i.e. an accessibility-*ish* DOM snapshot.
3. The extension service worker talks to the Python app via **Native Messaging**
   (`runtime.connectNative` / `sendNativeMessage`); content scripts must relay
   through the service worker (Native Messaging APIs are **not** available in
   content scripts).

**Sources:**  
https://developer.chrome.com/docs/extensions/develop/concepts/content-scripts  
https://developer.chrome.com/docs/extensions/reference/api/scripting  
https://developer.chrome.com/docs/extensions/develop/concepts/native-messaging  
https://developer.chrome.com/docs/extensions/reference/api/tabs (`tabs.query` for
active tab; host permissions / `activeTab` for privileged tab fields and
injection)

**Can see**

- Main-frame DOM the content script shares with the page (isolated JS world,
  shared DOM):
  https://developer.chrome.com/docs/extensions/develop/concepts/content-scripts
- Open shadow roots via `element.shadowRoot` (DOM standard: open mode exposes
  the tree; closed does not):
  https://dom.spec.whatwg.org/#shadowroot-mode
- Same-origin and cross-origin **iframe** documents **only if** a content
  script is injected into that frame. Injection is **per-frame** and each frame
  must independently match URL/`matches` (or `all_frames` + matching patterns);
  `match_origin_as_fallback` covers some `about:`/`data:`/`blob:` child frames:
  https://developer.chrome.com/docs/extensions/develop/concepts/content-scripts
  (“Specify frames” / “Inject in to related frames”)

**Cannot reliably see / do**

- **Closed** shadow trees from ordinary page JS / content-script DOM APIs
  (`shadowRoot` is null when mode is `"closed"`): WHATWG DOM above.
- **Canvas bitmap** as text: `<canvas>` maps to a canvas role; painted pixels
  are not DOM text. Fallback/`aria-*` content may be exposed separately
  (HTML-AAM): https://www.w3.org/TR/html-aam-1.0/#el-canvas
- Arbitrary execution of **speech-supplied JavaScript** — product must not do
  this (see §5); APIs *can* inject fixed extension functions via
  `scripting.executeScript`, which is why the grammar must stay deterministic.

**Fit for this product:** Best path to drive the **user’s everyday Chrome
profile** without turning on remote debugging. Aligns with prior research
deferral of in-page work to extension + Native Messaging
(`docs/research/voice-open-in-chrome.md`).

---

### (b) Chrome DevTools Protocol — `DOM.getDocument` / `Accessibility.getFullAXTree`

**What it is**

Attach to a debuggable Chrome target, then:

- `DOM.getDocument` — root DOM node / optional subtree; `pierce` optionally
  traverses iframes and shadow roots (default `false`).
- `DOM.getOuterHTML` — markup string; optional `includeShadowDOM`.
- `Accessibility.getFullAXTree` — computed AX nodes with `role`, `name`,
  `description`, `value`, optional `frameId` / `depth`.
- `Accessibility.queryAXTree` — filter subtree by `accessibleName` and/or
  `role` (explicitly designed for name+role queries).
- Input domain for synthetic clicks/keys once a node’s box is known.

**Sources:**  
https://raw.githubusercontent.com/ChromeDevTools/devtools-protocol/master/pdl/domains/DOM.pdl  
(`command getDocument`, `pierce`; `command getOuterHTML`, `includeShadowDOM`)  
https://raw.githubusercontent.com/ChromeDevTools/devtools-protocol/master/pdl/domains/Accessibility.pdl  
(`getFullAXTree`, `queryAXTree`, `AXNode.name` / `role`)  
https://raw.githubusercontent.com/ChromeDevTools/devtools-protocol/master/pdl/domains/Input.pdl  
https://developer.chrome.com/blog/remote-debugging-port  

**Chrome 136+ user-data-dir restriction (critical)**

From Chrome 136, `--remote-debugging-port` and `--remote-debugging-pipe` are
**ignored for the default Chrome data directory**. They must be paired with
`--user-data-dir` pointing at a **non-standard** directory. Chrome for Testing
is recommended for automation. Shipping CDP against the user’s default profile
is therefore **wrong for this product** (security posture + operational
conflict with the everyday session).

**Source:** https://developer.chrome.com/blog/remote-debugging-port  

**Can see**

- Full DOM with `pierce: true` (iframes + shadow roots in the attached target).
- Computed accessible names/roles via Accessibility domain (better match for
  speech than raw tag names).
- Cross-origin iframe documents when the debugger is attached to those targets /
  frames (protocol is browser-internal; still requires a debug session).

**Cannot / should not**

- Attach to the **default profile** under Chrome 136+ remote-debugging rules
  without a separate `--user-data-dir` (blog above).
- See canvas *pixels* as text via DOM/AX without author-provided accessible
  name / fallback (HTML-AAM canvas mapping).
- Be the MVP bridge for “user’s already-open personal Chrome.”

**Fit:** Strong for a **dedicated automation profile** / Chrome for Testing /
CI harness — **not** for the first shipping slice against the logged-in daily
browser.

---

### (c) macOS `AXUIElement` accessibility tree for Chrome

**What it is**

The OS X accessibility model exposes a hierarchy of accessible elements
(roles, labels/titles, values, supported actions such as press). Accessibility
clients query attributes and invoke actions; they do **not** receive the page’s
raw HTML source.

Apple’s own example is speech-driven UI: find a control by **title/label +
role**, then perform press — exactly the speech-matching pattern, but at the
**OS AX** layer rather than the web AccName layer.

**Sources:**  
https://developer.apple.com/library/archive/documentation/Accessibility/Conceptual/AccessibilityMacOSX/OSXAXmodel.html  
(“The Accessibility Hierarchy”; example screen reader matching titles/roles and
calling press)  
https://developer.apple.com/documentation/applicationservices/axuielement  
https://developer.apple.com/documentation/appkit/nsaccessibility  

Repo already flags platform AX sticky-snap as deferred / large:
`docs/BACKLOG.md` (“Cursor sticky snap… platform accessibility APIs”);
`docs/PRD.md` §7.4 stretch.

**Can see**

- What Chrome exposes to the platform accessibility API: roles, titles/labels,
  some values, focus, press/confirm-style actions (as Chrome implements AX).
- Roughly “what VoiceOver would navigate,” not CSS selectors or outerHTML.

**Cannot see**

- Raw HTML tags / full shadow DOM / CSSOM as markup.
- Reliable deep web semantics that Chrome does not mirror into AX (varies by
  Chrome version and page quality).
- Canvas pixel text unless exposed as an accessible name.
- Cross-platform parity (macOS-only; Windows/Linux need different AX bridges —
  conflicts with `AGENTS.md` “backends are the only OS-specific layer” unless
  carefully wrapped).

**Fit:** Useful later for OS chrome (tabs, omnibox) or as a coarse fallback;
**weaker** than an extension for precise in-page web control and for matching
web AccName computation.

---

### Visibility matrix (summary)

| Surface | Extension content script | CDP DOM + AX | macOS AXUIElement |
| --- | --- | --- | --- |
| Raw HTML / selectors | Yes (in injected frames) | Yes (`getOuterHTML`, query) | No |
| AccName / role | Approx. via DOM + aria / or CDP-like logic in page | Yes (`getFullAXTree` / `queryAXTree`) | Platform name/role only |
| Open shadow DOM | Yes (`shadowRoot`) | Yes (`pierce` / `includeShadowDOM`) | Only if Chrome flattens into AX |
| Closed shadow DOM | No via standard DOM | Often yes with pierce | Only if Chrome flattens into AX |
| Cross-origin iframe | Only if script injected into that frame (match patterns) | Yes when target/frame attached | Only Chrome’s AX projection |
| Canvas pixels as text | No | No | No |
| User’s default profile | Yes (normal extension) | **No** (Chrome 136+ without separate user-data-dir) | Yes (with Accessibility permission) |

---

## 3. Why visible accessible name beats raw tag name for speech

WAI-ARIA defines the **accessible name** as the name of a UI element — often
the **visible** text (e.g. button label “OK”) or an author-provided alternative
(`aria-label`, `aria-labelledby`, host-language labeling). Assistive tech
speaks role + name (e.g. “OK button”). Name computation prefers author
labeling features, then contents, per AccName.

**Sources:**  
https://www.w3.org/TR/wai-aria-1.2/#namecalculation  
https://www.w3.org/TR/accname-1.2/  
(CDP mirrors this: `AXNode.name`, `queryAXTree`’s `accessibleName` parameter —
Accessibility.pdl above.)

Speech “click on log in” aligns with the **name** “Log in”, not with the tag
`<button>` or a brittle CSS path. Tag names are invisible to users and collide
massively (`button` × N).

### Disambiguating two controls with the same name

Deterministic strategies (product policy; grounded in what descriptors can
carry):

1. **Role filter** — “click the log in **button**” vs link (`queryAXTree`-style
   role+name).
2. **Ordinal** — “first / second log in” over document order of matches.
3. **Context** — nearest landmark / heading / form name (“log in in the header”).
4. **Ask / refuse** — if still ambiguous, TTS confirmation per PRD §7.3 rather
   than guessing.
5. **Stable backend id** — once chosen, subsequent “type hello” targets the
   focused/last-resolved element id from the bridge.

Do **not** disambiguate by inventing free-form JS selectors from speech.

---

## 4. Recommended MVP vertical slices

### Slice A (first) — pure, unit-testable resolver (no live browser)

A pure function over an in-memory list of element descriptors:

```text
ElementDescriptor = {
  id: str,              # opaque backend id (extension node id, CDP backendNodeId, …)
  role: str,            # e.g. "button", "link", "textbox"
  name: str,            # accessible / visible name
  selector?: str,       # optional; opaque to the matcher
}
```

Phrase grammar (deterministic, PRD §7.3 / `AGENTS.md` voice rules):

- `click on <name>` / `click <name>`
- `type <text> into <name>` / `type <text>` (uses last focused / last matched
  textbox)

Resolver output: modality-neutral `Intent` values consumed by the Action
Mapper (extend `IntentType`; never call Chrome from `voice/`).

**Unit-test seam (hardware-free):** fixtures of descriptor lists → expected
intent or `AMBIGUOUS` / `NOT_FOUND`. This matches `AGENTS.md` (“unit tests:
… intent parsing”) and the prior open-URL research’s “parser fixtures first”
pattern (`docs/research/voice-open-in-chrome.md`).

Repo contracts to respect:

- `gesture_control/backends/base.py` — every injection path honors `SafePause`.
- `AGENTS.md` — voice → `Intent` → Action Mapper → backend; no OS/browser calls
  from `voice/`.
- `docs/PRD.md` §7.3 — deterministic grammar first; §7.5 — safe-pause mandatory.

### Slice B (later) — Chrome bridge for the user’s profile

Prefer **(a) extension + Native Messaging**:

1. Extension lists descriptors for the **active https tab**
   (`tabs.query({active, lastFocusedWindow})` + content-script walk).
2. Native host (Python side of this app) receives descriptors / sends
   `click(id)` / `focus(id)` / `type(id, text)` commands that the content
   script performs via DOM APIs (`element.click()`, `focus()`, `value` /
   `InputEvent` — fixed operations, not `eval(speech)`).
3. New `InputBackend` methods (or a narrow `BrowserBridge` called only from the
   mapper) must still check `safe_pause` before acting
   (`gesture_control/backends/base.py`; `AGENTS.md` safety invariant).

**Do not ship CDP against the default profile** (Chrome 136+ blog). CDP may
appear later only with an explicit separate `--user-data-dir` / Chrome for
Testing for automated QA — track in `docs/BACKLOG.md` if needed.

---

## 5. Safety constraints (in scope for design)

| Rule | Why / source |
| --- | --- |
| All click/type/open paths gate on `SafePause` | `gesture_control/backends/base.py`; `AGENTS.md` safety-critical invariant; `docs/PRD.md` §7.5 |
| Only act on **https** pages the tool opened **or** the front Chrome window the user is driving with this feature enabled | Continues https allowlist posture from `docs/research/voice-open-in-chrome.md`; reduces drive-by `file:` / `javascript:` risk |
| **No arbitrary JavaScript from speech** | Content-script CSP and XSS guidance warn that injecting untrusted strings is dangerous: https://developer.chrome.com/docs/extensions/develop/concepts/content-scripts ; keep a fixed command enum |
| Native Messaging host validates extension origin; service worker validates sender before forwarding | https://developer.chrome.com/docs/extensions/develop/concepts/native-messaging (warning on validating `sender.origin` / sanitizing payloads) |
| No CDP on default profile; no “attach to any Chrome on the LAN” | https://developer.chrome.com/blog/remote-debugging-port |
| Owner’s machine / consent (Accessibility permission if using AX; user-installed extension) | Apple AX model assumes an accessibility **client** on the same Mac: OSXAXmodel guide above |

Out of ethical/product scope (explicitly rejected): credential harvesting,
exfiltrating cookies via debugging, driving another person’s browser session.

---

## Recommendation

**Ship Slice A first** (pure speech → name/role resolver → `Intent`), then
**Slice B via a first-party Chrome extension + Native Messaging** that
snapshots accessibility-ish descriptors and performs fixed click/focus/type
ops on the active https tab. **Do not** use CDP against the default Chrome
profile. Treat macOS AX as an optional later fallback for OS chrome, not the
primary in-page HTML path. Keep matching on **accessible name + role**, with
ordinal/context/confirm for duplicates.

This continues the architecture in `AGENTS.md` / PRD §7.3 and upgrades the
deferred “in-page control” item from `docs/research/voice-open-in-chrome.md`
into an intentional milestone without violating Chrome 136 debugging rules.

---

## Not in the first implementation slice

- Live Chrome extension, Native Messaging host, or CDP client code.
- Attaching `--remote-debugging-port` to the user’s default profile.
- Reading raw HTML from the on-disk Chrome profile directory.
- macOS `AXUIElement` integration (evaluate after extension path).
- Closed-shadow / canvas-pixel / captcha / WebGL targeting.
- Cross-origin iframe coverage beyond what host permissions + `all_frames`
  naturally allow.
- Free-form LLM phrasing or speech → `eval` / `executeScript` of user strings
  (`docs/BACKLOG.md` optional Ollama remains deferred).
- Credential autofill, password-manager APIs, or cookie export.
- Windows/Linux browser bridges (macOS extension path first; backend interface
  stays abstract).

---

## Sources index

| Area | Primary source |
| --- | --- |
| Content scripts / DOM / frames / isolated world | https://developer.chrome.com/docs/extensions/develop/concepts/content-scripts |
| `chrome.scripting` | https://developer.chrome.com/docs/extensions/reference/api/scripting |
| `chrome.tabs` | https://developer.chrome.com/docs/extensions/reference/api/tabs |
| Native Messaging | https://developer.chrome.com/docs/extensions/develop/concepts/native-messaging |
| Remote debugging / Chrome 136+ profile rule | https://developer.chrome.com/blog/remote-debugging-port |
| CDP DOM | https://raw.githubusercontent.com/ChromeDevTools/devtools-protocol/master/pdl/domains/DOM.pdl |
| CDP Accessibility | https://raw.githubusercontent.com/ChromeDevTools/devtools-protocol/master/pdl/domains/Accessibility.pdl |
| CDP Input | https://raw.githubusercontent.com/ChromeDevTools/devtools-protocol/master/pdl/domains/Input.pdl |
| Shadow root open/closed | https://dom.spec.whatwg.org/#shadowroot-mode |
| Accessible name | https://www.w3.org/TR/wai-aria-1.2/#namecalculation ; https://www.w3.org/TR/accname-1.2/ |
| Canvas accessibility mapping | https://www.w3.org/TR/html-aam-1.0/#el-canvas |
| macOS AX model | https://developer.apple.com/library/archive/documentation/Accessibility/Conceptual/AccessibilityMacOSX/OSXAXmodel.html |
| `AXUIElement` / `NSAccessibility` | https://developer.apple.com/documentation/applicationservices/axuielement ; https://developer.apple.com/documentation/appkit/nsaccessibility |
| Repo contracts | `AGENTS.md`, `gesture_control/backends/base.py`, `docs/PRD.md` §7.3–7.5, `docs/BACKLOG.md`, `docs/research/voice-open-in-chrome.md` |
