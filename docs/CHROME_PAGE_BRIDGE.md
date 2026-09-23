# Chrome page bridge (macOS)

The page bridge is an opt-in local path from the Python voice app to the active
Google Chrome tab. It consists of a Manifest V3 extension, Chrome's Native
Messaging transport, a Python relay process, and a user-private Unix-domain
socket owned by the app. It opens no TCP port and never sends page data over
the network.

This slice deliberately does not wire the bridge into `ActionMapper` or
`MacOSInputBackend`. Callers can integrate the API after installing and testing
the transport independently.

## Install the unpacked extension

1. Open `chrome://extensions` in Google Chrome.
2. Enable **Developer mode**.
3. Click **Load unpacked** and select this repository's
   `chrome_extension/` directory.
4. Find **AI Gestures Page Bridge** and copy its 32-character **ID**. The ID is
   required explicitly; the installer does not inspect or modify a Chrome
   profile.

The extension requests only:

- `nativeMessaging`, to reach the one allow-listed local native host.
- Access to `https://*/*` through its content-script match, to index the active
  top-level HTTPS page.

It has no `tabs`, `scripting`, clipboard, storage, downloads, history, or
network-request permission. Although the content script is present on matching
pages, the service worker sends operations only to the active tab in the last
focused Chrome window. `chrome://`, `file://`, extension, and other non-HTTPS
pages are excluded.

## Install the native host

Use the same activated environment that runs the app:

```bash
source .venv/bin/activate
python -m pip install -e .
python scripts/manage_chrome_native_host.py install \
  --extension-id abcdefghijklmnopqrstuvwxyzabcdef
```

Replace the example ID with the exact ID copied in the previous section.
The installer validates Chrome's `a`-through-`p`, 32-character ID format. It
writes:

- `~/Library/Application Support/Google/Chrome/NativeMessagingHosts/com.ai_gestures.page_bridge.json`
- `~/Library/Application Support/AI Gestures Tool/native-host/com.ai_gestures.page_bridge`

The manifest allow-lists only
`chrome-extension://<the-explicit-extension-id>/`. The executable launcher
points to the Python interpreter running the installer (normally the current
`.venv`) and starts `gesture_control.browser.native_host`. Restart Chrome after
installing.

To uninstall without editing the Chrome profile:

```bash
python scripts/manage_chrome_native_host.py uninstall
```

## Connection test

1. Complete both installation sections and restart Chrome.
2. Open an ordinary HTTPS page containing a named link, button, checkbox, or
   text field, and leave that tab active.
3. From the activated project environment, run:

```bash
python - <<'PY'
from gesture_control.browser import ChromePageBridge

with ChromePageBridge(timeout=10.0) as bridge:
    snapshot = bridge.snapshot()
    print(snapshot.url)
    for element in snapshot.elements:
        print(element.element_id, element.role, repr(element.name))
PY
```

The extension retries its local native-host connection, so the command may
take up to a few seconds after the app creates its socket. A disconnected error
means Chrome is not running the extension, the native host is not installed
for that extension ID, Chrome needs restarting, or the Python environment
recorded by the launcher no longer exists.

For broader manual QA, serve `chrome_extension/test_fixture.html` from an HTTPS
origin and use its labeled fields and buttons. It intentionally does not work
when opened directly as a `file://` URL.

## App integration API

`gesture_control.browser.ChromePageBridge` is a synchronous context manager.
Starting it creates a mode-`0600` Unix socket below a mode-`0700` user-owned
directory. It safely removes only stale Unix sockets owned by the current user.
The methods are:

- `snapshot() -> PageSnapshot`
- `click(target_id)`
- `focus(target_id)`
- `type_text(target_id, text)`
- `type_and_submit(target_id, text)`

Every request has a generated request ID and a bounded timeout. IDs returned by
`snapshot()` are opaque and stable for the life of that page element; request a
new snapshot after navigation or DOM replacement. The extension and Python
ends both reject extra fields, unknown operation names, oversized text, invalid
JSON, and oversized Native Messaging frames. No operation evaluates speech,
JavaScript, selectors, or arbitrary code.

## Known limitations

- CAPTCHA and other anti-automation controls are not supported.
- Closed shadow DOM is not visible to the content script.
- Canvas/WebGL controls have no indexable DOM elements.
- Cross-origin iframe content is not indexed; only the top-level page is used.
- Elements without an accessible-ish name (`aria-label`, associated label,
  placeholder, visible text, or title) are omitted.
- Highly dynamic pages can replace an element after a snapshot; the operation
  then fails and the caller must request a fresh snapshot.
- Form submission requires the target textbox to be inside a form.
