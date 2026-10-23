# Manual QA Checklists

Hardware-dependent behavior (real camera, real mouse cursor, real microphone)
can't be fully covered by automated `pytest` unit tests. Each milestone that
touches hardware paths gets a checklist here, checked off manually before the
milestone's commit/tag is considered done.

## Voice — open a named site in Google Chrome

Wake word and microphone speech-to-text are not part of this slice. The
phrase is passed on the command line so the open path can be checked without
a mic.

- [ ] `python -m gesture_control.app --command "open cursor webpage"` opens
      https://cursor.com in Google Chrome (not Safari or another default
      browser).
- [ ] `python -m gesture_control.app --command "open apple website"` opens
      https://www.apple.com in Google Chrome.
- [ ] `python -m gesture_control.app --command "open my bank"` prints an error
      and does not open a tab.
- [ ] A paused `MacOSInputBackend` does not call Chrome. This is covered by
      unit tests; `--command` starts its own unpaused process, so the hotkey
      in a separate `--control` session does not block it.

## Voice — Google Chrome keyboard navigation (macOS)

This slice uses deterministic command-line phrases, not a microphone, wake
word, or TTS. Focus Google Chrome before each navigation command.

- [ ] `--command "next tab"` and `--command "previous tab"` select the
      expected adjacent Chrome tabs.
- [ ] `--command "new tab"` opens a tab and `--command "close tab"` closes it.
- [ ] `--command "back"` and `--command "forward"` move through the focused
      tab's history.
- [ ] `--command "refresh"` reloads the focused tab.
- [ ] A paused `MacOSInputBackend` sends no navigation shortcut (unit-covered).
- [ ] Extra words such as `next tab now` are rejected without sending keys.
- [ ] One-shot `--command` navigation does not require the optional page bridge.

## Voice — local microphone runtime (macOS)

Install with `python -m pip install -e ".[voice]"`. Grant the terminal
Microphone and Accessibility permissions. The first `tiny.en` run may need
network access to download model files; audio transcription is local and no
recording is uploaded.

- [ ] `python -m gesture_control.app --voice` prints model/microphone guidance,
      waits through room silence, and remains running for multiple commands.
- [ ] Saying `next tab`, `previous tab`, `new tab`, `close tab`, `back`,
      `forward`, and `refresh` performs the matching action in focused Chrome.
- [ ] Initial speech is not clipped, and a completed short phrase dispatches
      after trailing silence without requiring a key press.
- [ ] Empty/no-speech transcription is ignored, and an unknown phrase prints
      unrecognized feedback without injecting keyboard or browser input.
- [ ] Control+Option+Command+P blocks/resumes actions for the entire voice
      session while recording and transcription continue.
- [ ] Ctrl+C exits cleanly and releases the microphone and hotkey listener.
- [ ] No wake word or TTS occurs; listening begins only after explicit
      `--voice` startup.

## Voice — browser-wide vocabulary (macOS)

Focus Google Chrome and keep the SafePause hotkey available.

- [ ] Named aliases for Amazon, Google, YouTube, GitHub, Cursor, and Apple
      open the expected HTTPS site; `open example.com` upgrades to HTTPS.
- [ ] localhost, IP/private hosts, credentials, whitespace-bearing hosts,
      `http:`, `file:`, and `javascript:` inputs open nothing.
- [ ] `close current page`, next/previous-tab variants, `refresh current page`,
      and `reopen closed tab` send the expected fixed Chrome shortcut.
- [ ] `search for literal test; text` focuses Chrome's omnibox, types that
      literal query, and submits it.
- [ ] `page up/down`, small/large scrolls, explicit 1-10 page counts, and
      top/bottom scroll in the documented direction.
- [ ] Holding a plain spoken `scroll down` longer increases its bounded
      magnitude, while `scroll down 2 pages` remains two pages.
- [ ] Control+Option+Command+P blocks open, navigation, search, and scrolling.

## Voice — live Chrome page controls

Complete the setup in `docs/CHROME_PAGE_BRIDGE.md`, restart Chrome, open an
ordinary HTTPS page, and start `--voice`.

- [ ] `click <accessible button/link name>` activates one unique named control.
- [ ] `focus search` and `click the search box` focus the unique named textbox.
- [ ] `focus Chrome search bar`, then `type unit test`, then `enter` or `done`
      focuses Chrome's omnibox, writes literal text, and submits it.
- [ ] `focus app search bar`, then `type unit test`, then `enter` or `done`
      focuses one active-page HTML search field, writes text, and submits it.
      With multiple page search fields, focus command does nothing.
- [ ] `look up hello world` submits the query and leaves the page field
      unfocused; `clear search` then focuses the unique visible search field and
      clears it. `delete line` has the same select-all-and-clear behavior.
- [ ] In a supported page search field, `type hello world` then `delete word`
      leaves `hello`, even if the caret was previously in the middle.
- [ ] In a supported page search field or named contenteditable composer,
      `unfocus` or `stop focus` removes focus without changing its text. The
      same commands do nothing to an unrelated focused page element.
- [ ] `type delete word` remains literal typing, and `search for delete word`
      remains a search query; neither is consumed as an edit command.
- [ ] `type <value> into <field>` replaces the named field value and dispatches
      normal input/change events.
- [ ] On Amazon or another page with one named search textbox, `search for X`
      types and submits X; without a page search box it falls back to omnibox.
- [ ] Ambiguous duplicate names do not guess or mutate the page.
- [ ] Paused input blocks click, focus, type, submit, and focused-field edits at
      the backend.
- [ ] Disconnecting/uninstalling the extension produces actionable feedback;
      browser-wide navigation/search/scroll commands continue working.

## M1 — Camera + hand landmark pipeline

> Model/inference correctness (camera-free) is confirmed via
> `python tests/manual/verify_hand_landmarker.py` -- run this first if you
> suspect a regression, since it isolates the model/graph from the camera
> and reproduces the crash class documented in `docs/KNOWN_ISSUES.md`
> without needing a webcam. The mediapipe==1.0.x crash reported against
> `--debug` with a real camera has been root-caused and fixed (pinned to
> `mediapipe>=0.10.30,<0.11`); **please re-run `--debug` once more** to
> confirm the live camera loop itself is now fully clean end-to-end and
> check off the items below.

- [ ] `python -m gesture_control.app --debug` opens a window showing the live
      webcam feed.
- [ ] A detected hand shows all 21 MediaPipe landmarks overlaid, updating at an
      interactive framerate (no visible lag/freeze).
- [ ] Landmark overlay tracks correctly for both left and right hands.
- [ ] App exits cleanly (no orphaned camera handle/process) on quit.

## M2 — Virtual mouse v1

- [ ] With Terminal granted macOS Accessibility permission, `python -m
      gesture_control.app --debug --control` starts without an input-backend
      permission error.
- [ ] Moving the index fingertip moves the on-screen cursor smoothly and stays
      spatially on-track with the finger (no multi-frame trail, no jitter, no
      runaway drift, no single-pixel hunting while the hand is held still).
      Optional A/B if pinch flex walks clicks: `--cursor-point index_mcp` or
      `--cursor-point palm`.
- [ ] A pinch (thumb + index) reliably registers as a single click on a
      real target (e.g., a Dock icon), without fingertip flex moving the
      cursor during pinch approach or while pinched.
- [ ] Reaching screen corners does not require extreme arm travel; if it
      does, raise `--edge-margin` (e.g. `0.2`). If the pointer overshoots near
      edges, lower it (e.g. `0.1`).
- [ ] The safe-pause global hotkey immediately stops all cursor/click
      injection while actively gesturing, and a second press resumes it.
- [ ] Releasing the pinch does not produce a spurious extra click.

## M3 — Gesture vocabulary

- [ ] Double-pinch within the configured window registers as a double-click.
- [ ] Middle-finger pinch registers as a right-click and opens a context menu.
- [ ] Pinch-and-hold + move performs a drag (e.g., moves a desktop icon).
- [ ] Dwell-click (hover N ms) triggers a click without any pinch.
- [ ] Fist gesture pauses tracking; cursor does not move while repositioning
      the hand.
- [ ] Swipe left/right switches tabs/windows as configured.
- [ ] Swipe up/down scrolls in the expected direction.
- [ ] Pinch-spread zooms in/out on a real page.

## M4 — Cross-platform backend

- [ ] (macOS) All above still pass after the `InputBackend` refactor.
- [ ] (Windows, if available) Cursor move + click + scroll verified.
- [ ] (Linux X11, if available) Cursor move + click + scroll verified.
- [ ] (Linux Wayland, if available) `ydotoold` running; cursor move + click
      verified with documented setup steps.

## M5 — Voice agent

- [ ] Load `chrome_extension/` unpacked, install the native host with its
      explicit extension ID (`./scripts/setup_page_bridge.sh`), restart Chrome,
      and confirm `ChromePageBridge` snapshots only the active top-level HTTPS
      (or loopback fixture) tab.
- [ ] On the HTTPS-served or loopback `webassign_fixture.html`, voice/phrases
      `answer is 42` and `submit answer` fill the Answer box and click Submit
      Answer even when the control is outside a `<form>`.
- [ ] On the loopback `apple_fixture.html`, `--dump-page` lists
      `Search apple.com`, and `search for airpods` opens the collapsed search
      control then submits into the revealed combobox. Open-shadow `Buy` is
      listed.
- [ ] On a real `https://www.apple.com` tab, `--dump-page` shows
      `Search apple.com`; `search for macbook` drives site search (or omnibox
      fallback if the control is ambiguous).
- [ ] On the HTTPS-served `chrome_extension/test_fixture.html`, click, focus,
      type, type-and-submit, and checkbox click all work using snapshot IDs.
- [ ] `chrome://extensions`, a `file://` fixture, and a non-active HTTPS tab
      cannot be operated through the bridge.
- [ ] Stopping Chrome produces an actionable disconnected/timeout error and
      leaves no TCP listener.
- [ ] Saying the wake word triggers listening (visual/audio cue shown).
- [ ] Each implemented Chrome command executes end-to-end from local
      microphone audio with no network access after the model is cached.
- [ ] TTS confirmation is audible and matches the executed action.
- [ ] Disabling the mic via tray icon stops wake-word listening.

### M5 streaming voice (manual; blocks default flip)

Run from the repo venv on macOS with the Chrome page bridge connected.
Streaming STT is Chrome Web Speech (`--voice-stt web_speech`, the default):

```bash
python -m gesture_control.app --voice --voice-mode streaming
```

Allow the microphone in the separate voice-control window and click
**Start microphone**. Leave that window open. Local Moonshine / MLX backends
remain available via `--voice-stt`.

- [ ] Control window opens, Start microphone shows **Listening**, and a spoken
      **next browser** (or **close browser** / **previous browser**) prints a
      step report without waiting on the current site.
- [ ] With a normal Chrome browsing window focused, those navigation commands
      affect only that window's active tab and do not change window focus.
      With the Web Speech control window focused, they are ignored rather than
      navigating or closing the control page.
- [ ] On a page with one text box, **type what is your name into input** types
      that sentence. With the bridge disconnected, the same phrase still types
      into the focused field.

Expect ~0.1 s debounce for tab/scroll and up to ~0.6 s hold before free-text
actions (type / ask / search / page click) flush. Destructive clicks
(buy / submit / checkout / …) wait until you say **confirm**.

- [ below baseline ] Held-out accuracy: `python tests/manual/verify_moonshine_streaming.py --live --repair`
      scores at least 90% brand keywords. Prefer the expanded corpus:
      `python tests/manual/verify_moonshine_streaming.py --corpus --repair`
- [works ] `gesture-control --voice --voice-mode streaming`: say **open reddit**; Chrome
      opens Reddit.
- [ doesnt' fully work ] Same session: **open amazon and scroll down** — Amazon opens before you
      finish the sentence.
- [doesn't work ] **open amazon and click orders** after Amazon is ready (Account & Lists →
      Orders or equivalent).
- [ works but buggy ] Notes macro: **open notes then new note then type buy milk and eggs then
      press enter**.
- [ doesn't work ] **ask claude …** and **ask chatgpt …** while logged in; drop assistants
      whose composer does not autofocus (record in `docs/BACKLOG.md`).
- [ doesn't work] Press SafePause mid-queue; queued steps must not dispatch after resume.
- [must say in one line or doesn't work ] Say **cancel** while a step waits on readiness; pending work is cancelled.
- [ open tasks, can't cancel too quick ] Regression: `gesture-control --voice --voice-mode utterance` still behaves
      as before.

## Focused-field editing

- [ ] Focus a multi-line text area, put the cursor in the middle line, and say
      **delete line**. Only that line disappears. The lines above and below stay.
- [ ] The same command in a single-line input clears that input.
- [ ] **delete line** works in a normal text field, not only a search box.

## Voice pill UI (manual; needs Chrome and a microphone)

- [ ] `cd ui && npm run build`, then `python -m gesture_control.app --voice
      --voice-mode streaming`: a small pill window opens (not a full page).
- [ ] Allow the mic once; the soundwave bars move while you talk and sit flat
      when you are silent.
- [ ] Say **next tab**: interim words appear while speaking, then "Done:
      navigate browser" briefly, then back to "Say a command".
- [ ] Say **click a thing that does not exist**: the pill turns red with a reason.
- [ ] Flip the switch off: wave goes flat, text reads "AI assistant is off", and
      saying **next tab** does nothing. Flip it on: commands work again.
- [ ] Press the SafePause hotkey, say a command: pill shows "Input paused" and
      nothing is dispatched.
- [ ] Stop the Python process: pill shows "Reconnecting to assistant…".
- [ ] Deny the mic in Chrome: pill shows "Microphone blocked" (and not after the
      switch is off).

## M6 — Accessibility layer

- [ ] First-run calibration wizard produces a usable gesture range for a new
      user.
- [ ] "Limited mobility" profile: full basic browsing session (scroll, click,
      switch tab) completed using only dwell-click + voice, no pinch.
- [ ] Every core action reachable using a single hand only.
- [ ] Gesture remapping in config actually changes runtime behavior.

## M7 — Polish & packaging

- [ ] Packaged build launches on a clean macOS machine following only
      `README.md`.
- [ ] Tray icon accurately reflects tracking/mic on-off state.
