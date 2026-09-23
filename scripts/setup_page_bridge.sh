#!/usr/bin/env bash
# Guided one-time setup for the Chrome page bridge (macOS).
#
# Usage:
#   ./scripts/setup_page_bridge.sh
#   ./scripts/setup_page_bridge.sh --extension-id <32-char-id>
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
venv_python="${repo_root}/.venv/bin/python"
extension_dir="${repo_root}/chrome_extension"
extension_id=""

usage() {
  cat <<'EOF'
Usage: ./scripts/setup_page_bridge.sh [--extension-id ID]

Installs the Native Messaging host for the unpacked AI Gestures Page Bridge
Chrome extension using this repo's .venv interpreter.

Steps this script performs:
  1. Ensures .venv exists (runs setup_env.sh --voice if needed)
  2. Opens chrome://extensions and reveals chrome_extension/ in Finder
  3. Installs the native host for the extension ID you provide
  4. Prints WebAssign / local fixture test commands
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --extension-id)
      extension_id="${2:-}"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      usage >&2
      exit 2
      ;;
  esac
done

if [[ ! -x "${venv_python}" ]]; then
  echo "Creating voice-enabled virtualenv..."
  "${repo_root}/scripts/setup_env.sh" --voice
fi

echo ""
echo "==> Load the unpacked Chrome extension"
echo "1. In chrome://extensions enable Developer mode"
echo "2. Click Load unpacked"
echo "3. Select: ${extension_dir}"
echo "4. Copy the 32-character extension ID under AI Gestures Page Bridge"
echo ""

open -a "Google Chrome" "chrome://extensions" 2>/dev/null || true
open -R "${extension_dir}" 2>/dev/null || true

if [[ -z "${extension_id}" ]]; then
  if [[ -t 0 ]]; then
    read -r -p "Paste the extension ID here: " extension_id
  else
    echo "error: pass --extension-id when stdin is not interactive" >&2
    exit 2
  fi
fi

extension_id="$(echo "${extension_id}" | tr -d '[:space:]')"
if [[ ! "${extension_id}" =~ ^[a-p]{32}$ ]]; then
  echo "error: extension ID must be exactly 32 letters a-p (Chrome format)" >&2
  exit 2
fi

echo ""
echo "==> Installing native host for ${extension_id}"
"${venv_python}" "${repo_root}/scripts/manage_chrome_native_host.py" install \
  --extension-id "${extension_id}"

echo ""
echo "Native host installed. Fully quit and reopen Google Chrome, then test:"
echo ""
echo "  # Local WebAssign-style fixture"
echo "  ${venv_python} scripts/serve_bridge_fixture.py"
echo "  # Open the printed http://127.0.0.1 URL in Chrome, then:"
echo "  source .venv/bin/activate"
echo "  python - <<'PY'"
echo "from gesture_control.browser import ChromePageBridge"
echo "with ChromePageBridge(timeout=10) as bridge:"
echo "    snap = bridge.snapshot()"
echo "    print(snap.url, snap.title)"
echo "    for el in snap.elements: print(el.element_id, el.role, el.name)"
echo "PY"
echo ""
echo "  # Live voice on WebAssign (HTTPS)"
echo "  python -m gesture_control.app --voice"
echo "  # Then say: answer is 42   /   submit answer"
echo ""
echo "Docs: docs/CHROME_PAGE_BRIDGE.md and docs/WEBASSIGN_VOICE.md"
