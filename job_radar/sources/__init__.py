"""Job source adapters. Each one implements `fetch() -> Iterable[RawJob]`."""

from __future__ import annotations

from typing import Callable, Iterable

from job_radar.models import RawJob

# A Source is any zero-arg callable returning RawJobs.
Source = Callable[[], Iterable[RawJob]]
