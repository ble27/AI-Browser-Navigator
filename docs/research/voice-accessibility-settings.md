# Voice accessibility settings

What the pill's settings panel changes, and the sources those choices come from.
This is a product note, not a conformance claim.

## Sources

- [WCAG 2.2, Success Criterion 2.2.1 Timing Adjustable](https://www.w3.org/WAI/WCAG22/Understanding/timing-adjustable.html).
  When a time limit is essential to the interaction, the user needs a way to
  extend it. Dictation commits text after a quiet pause. That pause is a time
  limit.
- [WCAG 2.2, Success Criterion 1.4.4 Resize Text](https://www.w3.org/WAI/WCAG22/Understanding/resize-text.html).
  Text should be enlargeable without losing the control.
- [WCAG 2.2, Success Criterion 1.4.3 Contrast (Minimum)](https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum.html).
  Text against its background needs enough contrast. The pill is already light
  on black; high contrast pushes the muted status text up as well.
- [Apple Voice Control](https://support.apple.com/guide/mac-help/use-voice-control-mh40719/mac).
  Mac users who drive the computer by voice expect commands for scrolling and
  for turning features on and off, and they expect those commands to be
  adjustable rather than one fixed size.
- This repo's accessibility profiles in `docs/PRD.md` (Standard, Limited
  mobility, Voice-primary). Voice-primary means the core actions, including
  scroll, stay available without a precise hand gesture.

## Settings that follow from that

| Setting | Choices | Why |
| --- | --- | --- |
| Scroll distance | Small (1 page), Medium (3), Large (6) | A plain "scroll down" used to scale with how long the utterance was. Voice users cannot reliably hold a sound to pick a distance. An explicit size is easier to repeat. "scroll down 2 pages" and "scroll a little" still win over the setting. |
| Typing response | Fast (0.2 s), Steady (0.6 s) | Fast types soon after the words stop changing. Steady is the old wait, for someone who pauses inside a sentence. This is the timing-adjustable control. |
| Text size | Default, Large | Larger status text in the pill. |
| High contrast | Off, On | Status text stays near white instead of gray. |

Safe pause, the on/off switch, and the "say confirm" gate for destructive
clicks stay outside this panel. Those are safety controls, not preferences.
