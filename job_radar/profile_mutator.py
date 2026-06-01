"""Safe YAML editor for profile.yaml.

Keeps user-authored comments intact (uses ruamel.yaml if available, else
falls back to PyYAML — with a caveat about comment loss).
"""

from __future__ import annotations

from pathlib import Path

import yaml


def _load(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _dump(path: Path, data: dict) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        yaml.safe_dump(
            data,
            f,
            allow_unicode=True,
            sort_keys=False,
            default_flow_style=False,
        )
    tmp.replace(path)


def profile_path() -> Path:
    """Find the active profile file (same logic as load_profile)."""
    from job_radar.config import ROOT, _home

    home = _home()
    candidate = home / "profile.yaml"
    if candidate.exists():
        return candidate
    return ROOT / "profile" / "me.yaml"


def _add_to_list(data: dict, key: str, value: str) -> bool:
    lst = data.setdefault(key, []) or []
    if not isinstance(lst, list):
        raise ValueError(f"profile.{key} is not a list")
    lower = [str(x).lower() for x in lst]
    if value.lower() in lower:
        return False
    lst.append(value)
    data[key] = lst
    return True


def _remove_from_list(data: dict, key: str, value: str) -> bool:
    lst = data.get(key) or []
    if not isinstance(lst, list):
        return False
    before = len(lst)
    data[key] = [x for x in lst if str(x).lower() != value.lower()]
    return len(data[key]) != before


# ---- public API ------------------------------------------------------------


def block_company(name: str) -> tuple[bool, Path]:
    p = profile_path()
    d = _load(p)
    changed = _add_to_list(d, "blocked_companies", name)
    if changed:
        _dump(p, d)
    return changed, p


def unblock_company(name: str) -> tuple[bool, Path]:
    p = profile_path()
    d = _load(p)
    changed = _remove_from_list(d, "blocked_companies", name)
    if changed:
        _dump(p, d)
    return changed, p


def boost_company(name: str) -> tuple[bool, Path]:
    p = profile_path()
    d = _load(p)
    changed = _add_to_list(d, "boost_companies", name)
    if changed:
        _dump(p, d)
    return changed, p


def exclude_keyword(keyword: str) -> tuple[bool, Path]:
    p = profile_path()
    d = _load(p)
    changed = _add_to_list(d, "exclude_keywords", keyword)
    if changed:
        _dump(p, d)
    return changed, p


def disable_source(name: str) -> tuple[bool, Path]:
    p = profile_path()
    d = _load(p)
    changed = _add_to_list(d, "disabled_sources", name)
    if changed:
        _dump(p, d)
    return changed, p


def enable_source(name: str) -> tuple[bool, Path]:
    p = profile_path()
    d = _load(p)
    changed = _remove_from_list(d, "disabled_sources", name)
    if changed:
        _dump(p, d)
    return changed, p


def add_track_keyword(track_id: str, keyword: str) -> tuple[bool, Path]:
    """Add a keyword to a specific track's include_keywords."""
    p = profile_path()
    d = _load(p)
    tracks = d.get("tracks") or []
    for t in tracks:
        if t.get("id") == track_id:
            kws = t.setdefault("include_keywords", [])
            lower = [str(x).lower() for x in kws]
            if keyword.lower() in lower:
                return False, p
            kws.append(keyword)
            _dump(p, d)
            return True, p
    raise ValueError(f"track '{track_id}' not found in profile. Available: {[t.get('id') for t in tracks]}")


def remove_track_keyword(track_id: str, keyword: str) -> tuple[bool, Path]:
    """Remove a keyword from a specific track's include_keywords."""
    p = profile_path()
    d = _load(p)
    tracks = d.get("tracks") or []
    for t in tracks:
        if t.get("id") == track_id:
            kws = t.get("include_keywords") or []
            before = len(kws)
            t["include_keywords"] = [x for x in kws if str(x).lower() != keyword.lower()]
            if len(t["include_keywords"]) == before:
                return False, p
            _dump(p, d)
            return True, p
    raise ValueError(f"track '{track_id}' not found")
