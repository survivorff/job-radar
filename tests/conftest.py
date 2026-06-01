"""Shared fixtures: isolate each test's filesystem + reset cached singletons."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _isolate_env(tmp_path, monkeypatch):
    import job_radar.config as config_mod
    import job_radar.db as db_mod
    import job_radar.logging_ as logging_mod

    # Reset cached singletons so each test gets a fresh Settings()
    config_mod._settings = None
    db_mod._engine = None
    db_mod._Session = None
    logging_mod._CONFIGURED = False

    # Provide fresh paths via env (pydantic-settings picks these up, but we
    # also just patch ROOT to keep things simple for dev paths).
    data = tmp_path / "data"
    runs = tmp_path / "runs"
    logs = tmp_path / "logs"
    for p in (data, runs, logs):
        p.mkdir(parents=True, exist_ok=True)

    # Clear SMTP vars so tests never try real send.
    for var in ("SMTP_USER", "SMTP_PASS", "SMTP_TO", "SMTP_FROM"):
        monkeypatch.delenv(var, raising=False)

    # Monkey-patch paths on the freshly-constructed Settings instance.
    original_get = config_mod.get_settings

    def fresh_get():
        s = original_get()
        s.data_dir = data
        s.runs_dir = runs
        s.logs_dir = logs
        s.ensure_dirs()
        return s

    monkeypatch.setattr(config_mod, "get_settings", fresh_get)
    # Also patch the name as seen from other modules' import sites.
    monkeypatch.setattr("job_radar.db.get_settings", fresh_get)
    monkeypatch.setattr("job_radar.trace.get_settings", fresh_get)
    monkeypatch.setattr("job_radar.logging_.get_settings", fresh_get)
    yield
