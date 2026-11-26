"""Cooperative, host-owned search limits. Units count candidate evaluations/calls."""
import math
import time
from collections import Counter


class SearchStopped(Exception):
    """Construction stopped before completion; an earlier complete attempt may exist."""
    def __init__(self, reason, best=None):
        super().__init__(reason)
        self.best = best


class SearchBudget:
    def __init__(self, max_operations=100_000, time_limit_seconds=10.0,
                 should_cancel=None, *, clock=time.monotonic):
        if type(max_operations) is not int or not 0 <= max_operations <= 10_000_000:
            raise ValueError("max_operations must be an integer in 0..10000000")
        if (isinstance(time_limit_seconds, bool) or not isinstance(time_limit_seconds, (int, float))
                or not math.isfinite(time_limit_seconds) or time_limit_seconds < 0):
            raise ValueError("time_limit_seconds must be finite and nonnegative")
        self.limit = max_operations
        self.time_limit_seconds = float(time_limit_seconds)
        self.used = 0
        self.counts = Counter()
        self.clock = clock
        self.started = clock()
        self.deadline = self.started + time_limit_seconds
        self.should_cancel = should_cancel or (lambda: False)
        self.reason = None

    @property
    def elapsed(self):
        return max(0.0, self.clock() - self.started)

    def check(self):
        if self.reason is not None:
            return False
        try:
            cancelled = self.should_cancel()
        except Exception:
            self.reason = "cancellation_error"
            return False
        if cancelled:
            self.reason = "cancelled"
        elif self.clock() >= self.deadline:
            self.reason = "deadline"
        elif self.used >= self.limit:
            self.reason = "operation_budget"
        return self.reason is None

    def consume(self, category="search"):
        if not self.check():
            return False
        self.used += 1
        self.counts[category] += 1
        return True

    def require(self, category="construction"):
        if not self.consume(category):
            raise SearchStopped(self.reason)
