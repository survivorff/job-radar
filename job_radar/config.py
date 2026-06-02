"""Configuration loading.

Layers:
  env defaults  ←  .env  ←  profile/me.yaml  ←  CLI overrides
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parent.parent


def _home() -> Path:
    """Pick where data + user profile live.

    Priority:
      1. $JOB_RADAR_HOME (skill deployments should set this to ~/.job-radar)
      2. Repo root (dev mode)

    This lets us run the exact same code in dev (where data/ lives next to
    the source tree) and as a Claude/openclaw skill (where user config and
    database belong under ~/.job-radar so skill upgrades don't wipe them).
    """
    override = os.environ.get("JOB_RADAR_HOME")
    if override:
        return Path(override).expanduser()
    return ROOT


# ---------------------------- profile (yaml) --------------------------------


class Track(BaseModel):
    id: str
    priority: int = 99
    resume_version: str = "default"
    description: str = ""
    include_keywords: list[str] = Field(default_factory=list)
    required_any: list[str] = Field(default_factory=list)
    prefer_remote_overseas: bool = False
    ideal_jd_path: str | None = None


class Thresholds(BaseModel):
    embed_recall_cosine: float = 0.35
    llm_push_high: int = 90
    llm_push_med: int = 75
    llm_push_low: int = 60


class Budget(BaseModel):
    daily_llm_cny: float = 5.0
    per_job_max_cny: float = 0.02


class Profile(BaseModel):
    name: str
    resume_path: str | None = None
    tracks: list[Track]
    exclude_keywords: list[str] = Field(default_factory=list)
    seniority_allowlist: list[str] = Field(default_factory=list)
    seniority_blocklist: list[str] = Field(default_factory=list)
    location_allowlist: list[str] = Field(default_factory=list)
    # If true, non-remote JDs are dropped regardless of location allowlist.
    # Useful when the user ONLY wants remote work (full-time, part-time, contract).
    remote_only: bool = False
    # Employment preferences — purely advisory (surfaced in the email), not a
    # hard filter. LLM uses these as context when scoring.
    employment_types: list[str] = Field(default_factory=list)  # e.g. ["full-time", "part-time", "contract", "co-founder"]
    # Digest language: "bilingual" (EN+中文), "en", or "zh".
    digest_lang: Literal["bilingual", "en", "zh"] = "bilingual"
    exp_min_years: int = 0
    exp_accept_unspecified: bool = True
    # Per-company controls. Normalized matching (case-insensitive, contains).
    blocked_companies: list[str] = Field(default_factory=list)
    boost_companies: list[str] = Field(default_factory=list)
    # Per-source controls. Keys = source names from sources/registry.py.
    disabled_sources: list[str] = Field(default_factory=list)
    thresholds: Thresholds = Field(default_factory=Thresholds)
    budget: Budget = Field(default_factory=Budget)


def load_profile(path: Path | None = None) -> Profile:
    """Load profile YAML.

    Search order:
      1. explicit `path` arg
      2. $JOB_RADAR_HOME/profile.yaml (skill mode)
      3. <repo>/profile/me.yaml (your local profile, gitignored)
      4. <repo>/profile/example.yaml (fallback template)
    """
    if path is not None:
        chosen = path
    else:
        home = _home()
        chosen = home / "profile.yaml"
        if not chosen.exists():
            dev = ROOT / "profile" / "me.yaml"
            example = ROOT / "profile" / "example.yaml"
            chosen = dev if dev.exists() else example
    with chosen.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return Profile.model_validate(data)


# ---------------------------- env (.env) ------------------------------------


class Settings(BaseSettings):
    """Runtime settings pulled from .env + os.environ.

    In skill/deploy mode (`JOB_RADAR_HOME=~/.job-radar`), .env is read from
    that same user directory; in dev mode it's read from the repo root.
    """

    model_config = SettingsConfigDict(
        env_file=(str(_home() / ".env"), str(ROOT / ".env")),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # LLM (M2+)
    deepseek_api_key: str | None = Field(default=None, alias="DEEPSEEK_API_KEY")
    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY")
    anthropic_api_key: str | None = Field(default=None, alias="ANTHROPIC_API_KEY")
    anthropic_api_base: str | None = Field(default=None, alias="ANTHROPIC_API_BASE")
    scorer_model: str = Field(default="deepseek/deepseek-chat", alias="JOB_RADAR_SCORER_MODEL")

    # Email: Resend (preferred — HTTPS, works behind cloud egress firewalls)
    resend_api_key: str | None = Field(default=None, alias="RESEND_API_KEY")
    resend_domain_verified: bool = Field(default=False, alias="RESEND_DOMAIN_VERIFIED")

    @field_validator("resend_domain_verified", mode="before")
    @classmethod
    def _coerce_bool(cls, v):
        if v is None or v == "":
            return False
        if isinstance(v, bool):
            return v
        return str(v).strip().lower() in {"1", "true", "yes", "y", "on"}

    # Email (M1 primary channel)
    smtp_host: str = Field(default="smtp.gmail.com", alias="SMTP_HOST")
    smtp_port: int = Field(default=587, alias="SMTP_PORT")
    smtp_user: str | None = Field(default=None, alias="SMTP_USER")
    smtp_pass: str | None = Field(default=None, alias="SMTP_PASS")
    smtp_from: str | None = Field(default=None, alias="SMTP_FROM")
    smtp_to: str | None = Field(default=None, alias="SMTP_TO")

    # Budget
    daily_llm_budget: float = Field(default=5.0, alias="JOB_RADAR_DAILY_LLM_BUDGET")

    # Logs
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    # Paths (derived from _home())
    data_dir: Path = Field(default_factory=lambda: _home() / "data")
    runs_dir: Path = Field(default_factory=lambda: _home() / "runs")
    logs_dir: Path = Field(default_factory=lambda: _home() / "logs")

    def ensure_dirs(self) -> None:
        for p in (self.data_dir, self.runs_dir, self.logs_dir):
            p.mkdir(parents=True, exist_ok=True)

    @property
    def db_url(self) -> str:
        return f"sqlite:///{self.data_dir / 'radar.sqlite'}"

    @property
    def smtp_configured(self) -> bool:
        return bool(self.smtp_user and self.smtp_pass and self.smtp_to)


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
        _settings.ensure_dirs()
    return _settings
