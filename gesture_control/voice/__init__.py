"""Offline voice command pipeline.

The implemented macOS runtime records explicitly started microphone sessions,
transcribes locally with ``faster-whisper``, and sends deterministic intents
through the shared Action Mapper. Optional audio/model packages are lazily
imported, so gesture-only startup never requires them. Wake word, TTS, and the
live Chrome page bridge remain deferred.
"""
