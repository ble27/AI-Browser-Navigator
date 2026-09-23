"""Offline voice command pipeline.

Wake word (``openWakeWord``) -> offline speech-to-text (``faster-whisper``)
-> deterministic intent parser -> offline text-to-speech (``Piper``) for
confirmations. All dependencies in this package are optional and lazily
imported, so a gesture-only install never requires audio libraries.
Browser open-site phrases are parsed by :mod:`gesture_control.voice.browser`.
"""
