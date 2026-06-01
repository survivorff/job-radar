"""Render the current daily digest to /tmp/job_radar_digest.html and open it."""

from __future__ import annotations

import subprocess
from pathlib import Path

from job_radar.channels.digest import load_digest, render_digest_html, render_digest_subject


def main() -> None:
    d = load_digest("daily")
    html = render_digest_html(d)
    out = Path("/tmp/job_radar_digest.html")
    out.write_text(html, encoding="utf-8")
    print(f"Subject: {render_digest_subject(d)}")
    print(f"Wrote {out} ({len(html)} bytes)")
    try:
        subprocess.run(["open", str(out)], check=False)
    except Exception:
        pass


if __name__ == "__main__":
    main()
