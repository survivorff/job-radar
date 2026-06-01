"""Quick peek at a new feed's shape."""

import json
import sys

import httpx


def main() -> None:
    url = sys.argv[1]
    resp = httpx.get(url, timeout=20.0)
    print(f"status={resp.status_code}  size={len(resp.content)}b")
    if resp.headers.get("content-type", "").startswith("application/json"):
        d = resp.json()
        if isinstance(d, dict):
            for k, v in d.items():
                if isinstance(v, list):
                    print(f"  [{k}] list, len={len(v)}")
                    if v:
                        for key in list(v[0].keys())[:20]:
                            print(f"     · {key}")
                        print("     first item:")
                        print("     ", json.dumps(v[0], indent=2)[:400])
                    break
        elif isinstance(d, list):
            print(f"  list, len={len(d)}")
            if d:
                for key in list(d[0].keys())[:20]:
                    print(f"     · {key}")


if __name__ == "__main__":
    main()
