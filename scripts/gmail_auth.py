"""One-time Gmail OAuth helper.

Run on your LOCAL MACHINE (it opens a browser). Saves a refresh token
that the server then uses via HTTPS.

Usage:
  1. Create OAuth client at https://console.cloud.google.com/apis/credentials
     - Application type: "Desktop app"
     - Copy Client ID + Client Secret
  2. export GOOGLE_CLIENT_ID=...
     export GOOGLE_CLIENT_SECRET=...
  3. uv run python scripts/gmail_auth.py
  4. Browser opens, grant read-only Gmail scope
  5. Copy the resulting ~/.job-radar/gmail_token.json to the server:
       scp ~/.job-radar/gmail_token.json root@SERVER:/root/.job-radar/
"""

from __future__ import annotations

import http.server
import json
import os
import socketserver
import threading
import urllib.parse
import webbrowser
from pathlib import Path

import httpx

SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
REDIRECT_HOST = "127.0.0.1"
REDIRECT_PORT = 43731


class _CBHandler(http.server.BaseHTTPRequestHandler):
    code: str | None = None
    error: str | None = None

    def log_message(self, *args) -> None:  # silence stdout noise
        pass

    def do_GET(self) -> None:  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)
        if "code" in params:
            _CBHandler.code = params["code"][0]
            body = b"<h2>Gmail auth OK. You can close this window.</h2>"
        elif "error" in params:
            _CBHandler.error = params["error"][0]
            body = f"<h2>Error: {params['error'][0]}</h2>".encode()
        else:
            body = b"<h2>Waiting for Google…</h2>"
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(body)


def main() -> None:
    client_id = os.environ.get("GOOGLE_CLIENT_ID")
    client_secret = os.environ.get("GOOGLE_CLIENT_SECRET")
    if not (client_id and client_secret):
        print("ERROR: set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET in the environment first.")
        print(
            "Create credentials at https://console.cloud.google.com/apis/credentials"
            " (Application type: Desktop app)."
        )
        raise SystemExit(1)

    redirect_uri = f"http://{REDIRECT_HOST}:{REDIRECT_PORT}"
    # 1. open browser with consent URL
    consent = AUTH_URL + "?" + urllib.parse.urlencode(
        {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": SCOPE,
            "access_type": "offline",
            "prompt": "consent",
        }
    )
    print(f"Opening browser: {consent}")
    webbrowser.open(consent)

    # 2. listen for the redirect
    with socketserver.TCPServer((REDIRECT_HOST, REDIRECT_PORT), _CBHandler) as httpd:
        print(f"Waiting on {redirect_uri} ...")
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        while _CBHandler.code is None and _CBHandler.error is None:
            pass
        httpd.shutdown()

    if _CBHandler.error:
        raise SystemExit(f"OAuth error: {_CBHandler.error}")

    code = _CBHandler.code
    # 3. exchange for tokens
    resp = httpx.post(
        TOKEN_URL,
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
        },
        timeout=30.0,
    )
    resp.raise_for_status()
    data = resp.json()

    token = {
        "access_token": data["access_token"],
        "refresh_token": data.get("refresh_token"),
        "token_type": data.get("token_type", "Bearer"),
        "_expires_at": 0,
        "client_id": client_id,
        "client_secret": client_secret,
        "scope": SCOPE,
    }

    out = Path.home() / ".job-radar" / "gmail_token.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(token, indent=2))
    print(f"\n✅ Saved refresh token to {out}")
    print(f"   Now copy it to the server:")
    print(f"     scp {out} root@<server>:/root/.job-radar/gmail_token.json")


if __name__ == "__main__":
    main()
