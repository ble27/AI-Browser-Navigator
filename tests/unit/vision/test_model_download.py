"""Tests for gesture_control.vision.model_download.

Network access is monkeypatched out entirely so these tests are fast,
deterministic, and runnable offline as part of ``scripts/check.sh``.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from gesture_control.vision import model_download


def test_ensure_model_downloads_when_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A missing model file should trigger exactly one download call."""
    download_calls: list[tuple[str, str]] = []

    def fake_urlretrieve(url: str, filename: str) -> None:
        download_calls.append((url, filename))
        Path(filename).write_bytes(b"fake-model-bytes")

    monkeypatch.setattr(model_download.urllib.request, "urlretrieve", fake_urlretrieve)

    model_path = model_download.ensure_hand_landmarker_model(dest_dir=tmp_path)

    assert model_path == tmp_path / "hand_landmarker.task"
    assert model_path.read_bytes() == b"fake-model-bytes"
    assert len(download_calls) == 1


def test_ensure_model_skips_download_when_already_cached(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An existing cached model should short-circuit without hitting the network."""
    cached_path = tmp_path / "hand_landmarker.task"
    cached_path.write_bytes(b"already-here")

    def fail_if_called(url: str, filename: str) -> None:
        raise AssertionError("urlretrieve should not be called when the model is cached")

    monkeypatch.setattr(model_download.urllib.request, "urlretrieve", fail_if_called)

    model_path = model_download.ensure_hand_landmarker_model(dest_dir=tmp_path)

    assert model_path == cached_path
    assert model_path.read_bytes() == b"already-here"


def test_ensure_model_force_download_overwrites_cache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """force_download=True should re-fetch even if a cached copy exists."""
    cached_path = tmp_path / "hand_landmarker.task"
    cached_path.write_bytes(b"stale")

    def fake_urlretrieve(url: str, filename: str) -> None:
        Path(filename).write_bytes(b"fresh")

    monkeypatch.setattr(model_download.urllib.request, "urlretrieve", fake_urlretrieve)

    model_path = model_download.ensure_hand_landmarker_model(dest_dir=tmp_path, force_download=True)

    assert model_path.read_bytes() == b"fresh"


def test_ensure_model_raises_runtime_error_with_remediation_on_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A network failure should raise a clear, actionable RuntimeError, not leak an OSError."""

    def failing_urlretrieve(url: str, filename: str) -> None:
        raise OSError("network unreachable")

    monkeypatch.setattr(model_download.urllib.request, "urlretrieve", failing_urlretrieve)

    with pytest.raises(RuntimeError, match="Failed to download"):
        model_download.ensure_hand_landmarker_model(dest_dir=tmp_path)

    # No partially-written file should be left behind to confuse a future cache check.
    assert not (tmp_path / "hand_landmarker.task").exists()
