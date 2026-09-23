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
- [ ] `type <value> into <field>` replaces the named field value and dispatches
      normal input/change events.
- [ ] On Amazon or another page with one named search textbox, `search for X`
      types and submits X; without a page search box it falls back to omnibox.
- [ ] Ambiguous duplicate names do not guess or mutate the page.
- [ ] Paused input blocks click, focus, type, and submit at the backend.
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
      explicit extension ID, restart Chrome, and confirm `ChromePageBridge`
      snapshots only the active top-level HTTPS tab.
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
