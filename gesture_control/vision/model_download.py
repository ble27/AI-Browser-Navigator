"""Download and cache the MediaPipe HandLandmarker model bundle.

The ``.task`` model file is a ~7-8 MB binary asset that we do not want to
commit to git (see ``.gitignore``). Instead, it is fetched once on first use
and cached in a local ``models/`` directory at the repo root.
"""

from __future__ import annotations

import urllib.request
from pathlib import Path

# Official MediaPipe-hosted model bundle. See:
# https://developers.google.com/edge/mediapipe/solutions/vision/hand_landmarker
_MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/hand_landmarker/"
    "hand_landmarker/float16/latest/hand_landmarker.task"
)
_MODEL_FILENAME = "hand_landmarker.task"

# gesture_control/vision/model_download.py -> repo_root/models/
_DEFAULT_MODEL_DIR = Path(__file__).resolve().parent.parent.parent / "models"


def ensure_hand_landmarker_model(
    dest_dir: Path | None = None, *, force_download: bool = False
) -> Path:
    """Ensure the HandLandmarker model bundle exists locally, downloading it if needed.

    Args:
        dest_dir: Directory to cache the model file in. Defaults to a
            ``models/`` directory at the repository root.
        force_download: If ``True``, re-download even if a cached copy
            already exists (useful for recovering from a corrupt download).

    Returns:
        Path to the cached ``.task`` model file, ready to pass to
        MediaPipe's ``BaseOptions(model_asset_path=...)``.

    Raises:
        RuntimeError: If the model could not be downloaded, with remediation
            guidance (check network connection, or download manually).
    """
    directory = dest_dir if dest_dir is not None else _DEFAULT_MODEL_DIR
    directory.mkdir(parents=True, exist_ok=True)
    model_path = directory / _MODEL_FILENAME

    if model_path.exists() and not force_download:
        return model_path

    try:
        urllib.request.urlretrieve(
            _MODEL_URL, model_path
        )  # noqa: S310 (trusted, hardcoded HTTPS URL)
    except OSError as exc:
        # Clean up a partially-written file so a retry doesn't mistake it
        # for a valid cached model.
        model_path.unlink(missing_ok=True)
        raise RuntimeError(
            "Failed to download the MediaPipe HandLandmarker model from "
            f"{_MODEL_URL}. Check your network connection, or manually "
            f"download the file and place it at {model_path}."
        ) from exc

    return model_path
