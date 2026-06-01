"""Loguru setup. Called once at CLI entry."""

from __future__ import annotations

import sys

from loguru import logger

from job_radar.config import get_settings

_CONFIGURED = False


def setup_logging() -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return
    s = get_settings()
    logger.remove()
    logger.add(
        sys.stderr,
        level=s.log_level,
        format=(
            "<green>{time:HH:mm:ss}</green> "
            "<level>{level: <7}</level> "
            "<cyan>{name}</cyan>:<cyan>{line}</cyan> - {message}"
        ),
    )
    logger.add(
        s.logs_dir / "radar.log",
        level="DEBUG",
        rotation="5 MB",
        retention=10,
        enqueue=True,
    )
    _CONFIGURED = True
