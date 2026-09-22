# Manual QA Checklists

Hardware-dependent behavior (real camera, real mouse cursor, real microphone)
can't be fully covered by automated `pytest` unit tests. Each milestone that
touches hardware paths gets a checklist here, checked off manually before the
milestone's commit/tag is considered done.

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
- [ ] Moving the index fingertip moves the on-screen cursor smoothly (no
      jitter, no runaway drift).
- [ ] A pinch (thumb + index) reliably registers as a single click on a
      real target (e.g., a Dock icon), without fingertip jitter moving the
      cursor while pinched.
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

- [ ] Saying the wake word triggers listening (visual/audio cue shown).
- [ ] Each command in the grammar (`click`, `scroll down`, `switch tab`,
      `pause tracking`, ...) executes the correct action end-to-end offline
      (no network access during the test).
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
