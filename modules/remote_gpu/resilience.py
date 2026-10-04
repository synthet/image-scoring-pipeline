"""Bounded retry timing shared by runner clients."""

from __future__ import annotations

import math
import time
from dataclasses import dataclass
from email.utils import parsedate_to_datetime

from modules.remote_gpu.contract import RemoteGpuError


def positive_seconds(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
        raise RemoteGpuError(f"gpu_runner.{name} must be finite and positive")
    return float(value)


@dataclass(frozen=True)
class RetryPolicy:
    max_retries: int = 3
    base_delay_seconds: float = 1.0
    max_delay_seconds: float = 8.0
    budget_seconds: float = 30.0

    def __post_init__(self):
        if type(self.max_retries) is not int or not 0 <= self.max_retries <= 10:
            raise RemoteGpuError("gpu_runner.retry.max_retries must be an integer from 0 to 10")
        for name in ("base_delay_seconds", "max_delay_seconds", "budget_seconds"):
            positive_seconds(getattr(self, name), f"retry.{name}")
        if self.max_delay_seconds < self.base_delay_seconds:
            raise RemoteGpuError("gpu_runner.retry.max_delay_seconds must be at least base_delay_seconds")

    def delay(self, attempt, random_fn, retry_after=0.0):
        ceiling = min(self.max_delay_seconds, self.base_delay_seconds * 2 ** attempt)
        return max(ceiling * random_fn(), retry_after)


def retry_after_seconds(value, *, now=None):
    """Retry-After is either nonnegative delta-seconds or an HTTP date (RFC 9110)."""
    if not value:
        return 0.0
    try:
        if value.isdigit():
            delay = float(value)
        else:
            parsed = parsedate_to_datetime(value)
            if parsed.tzinfo is None:
                return 0.0
            delay = parsed.timestamp() - (time.time() if now is None else now)
        return max(0.0, delay) if math.isfinite(delay) else 0.0
    except (ValueError, OverflowError, TypeError):
        return 0.0
