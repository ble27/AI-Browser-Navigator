#!/usr/bin/env python3
"""Serve the local page-bridge fixtures over loopback HTTP.

Chrome's content script is allow-listed for http://127.0.0.1 and
http://localhost so WebAssign-style fixtures can be tested without a TLS
certificate. Production WebAssign pages continue to use HTTPS.
"""

from __future__ import annotations

import argparse
import functools
import http.server
import socketserver
from pathlib import Path


def main() -> int:
    """Run a loopback static file server for ``chrome_extension/`` fixtures.

    Returns:
        Process exit code.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1", help="Bind address (loopback only).")
    parser.add_argument("--port", type=int, default=8765, help="Bind port.")
    args = parser.parse_args()

    if args.host not in {"127.0.0.1", "localhost"}:
        raise SystemExit("Refusing to bind off-loopback; use 127.0.0.1 or localhost.")

    repo_root = Path(__file__).resolve().parents[1]
    extension_dir = repo_root / "chrome_extension"
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(extension_dir))

    with socketserver.TCPServer((args.host, args.port), handler) as httpd:
        base = f"http://{args.host}:{args.port}"
        print(f"Serving {extension_dir}")
        print(f"WebAssign-style fixture: {base}/webassign_fixture.html")
        print(f"Apple-style fixture:     {base}/apple_fixture.html")
        print(f"SEO naming fixture:      {base}/seo_fixture.html")
        print(f"Generic fixture:         {base}/test_fixture.html")
        print("Press Ctrl+C to stop.")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nStopped.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
