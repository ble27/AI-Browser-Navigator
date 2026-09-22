#!/usr/bin/env bash
# Create (or reuse) a project-local virtual environment and install the
# package in editable mode with development dependencies.
#
# Usage:
#   ./scripts/setup_env.sh            # gesture-only deps + dev tooling
#   ./scripts/setup_env.sh --voice     # also install the voice-agent extras
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
venv_dir="${repo_root}/.venv"

# Prefer a pinned, well-tested interpreter over whatever `python3` resolves
# to on the host, since MediaPipe/faster-whisper/openWakeWord are tested
# against 3.11/3.12, not necessarily the newest release.
#
# NOTE: Python 3.12.5 specifically has a known CPython `ast` module bug that
# breaks Black's AST safety checks (fixed in 3.12.6). 3.11 is listed first
# to sidestep that on machines that happen to have 3.12.5 installed; if your
# 3.12 is >=3.12.6, it works fine too.
find_python() {
  for candidate in \
    "/Library/Frameworks/Python.framework/Versions/3.11/bin/python3.11" \
    "/Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12" \
    python3.11 \
    python3.12; do
    if command -v "${candidate}" >/dev/null 2>&1; then
      echo "${candidate}"
      return 0
    fi
  done
  echo "error: no compatible Python (3.11 or 3.12) found on PATH." >&2
  exit 1
}

python_bin="$(find_python)"
echo "Using interpreter: ${python_bin} ($(${python_bin} --version))"

if [ ! -d "${venv_dir}" ]; then
  echo "Creating virtual environment at ${venv_dir}"
  "${python_bin}" -m venv "${venv_dir}"
fi

# shellcheck disable=SC1091
source "${venv_dir}/bin/activate"

pip install --upgrade pip

extras="dev"
if [[ "${1:-}" == "--voice" ]]; then
  extras="dev,voice"
fi

echo "Installing gesture-control[${extras}] in editable mode..."
pip install -e "${repo_root}[${extras}]"

echo ""
echo "Setup complete. Activate the environment with:"
echo "  source .venv/bin/activate"
