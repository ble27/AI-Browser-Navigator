#!/usr/bin/env bash
# Quality gate that must pass before any commit lands, per AGENTS.md:
# formatting, linting, static typing, and unit tests.
#
# Usage: ./scripts/check.sh [--fix]
#   --fix   Auto-format with black and auto-fix lint issues with ruff first.
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${repo_root}"

if [[ "${1:-}" == "--fix" ]]; then
  echo "==> black (auto-format)"
  black gesture_control tests
  echo "==> ruff (auto-fix)"
  ruff check --fix gesture_control tests
fi

echo "==> black --check"
black --check gesture_control tests

echo "==> ruff check"
ruff check gesture_control tests

echo "==> mypy"
mypy gesture_control

echo "==> pytest"
pytest

if command -v node >/dev/null 2>&1; then
  echo "==> node --test chrome_extension"
  node --test chrome_extension/*.test.js
fi

echo ""
echo "All checks passed."
