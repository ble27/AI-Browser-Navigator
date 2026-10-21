#!/usr/bin/env bash
# Quality gate for the pill UI: typecheck, unit tests, production build.
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${repo_root}/ui"

if [[ ! -d node_modules ]]; then
  echo "==> npm ci"
  npm ci --no-fund --no-audit
fi

echo "==> tsc"
npm run --silent typecheck
echo "==> vitest"
npm test --silent
echo "==> vite build"
npm run --silent build

echo ""
echo "UI checks passed."
