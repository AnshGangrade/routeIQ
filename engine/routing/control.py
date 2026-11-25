"""Trusted scheduling interface; no routes or executable code cross this boundary."""
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class InitialControl:
    construction: str
    config: object
    operation_slice: int


@dataclass(frozen=True)
class SearchAction:
    action: str = 'continue'
    operators: tuple[str, ...] = ()
    max_moves: int | None = None
    operation_slice: int = 10000


class StrategyController(Protocol):
    max_checkpoints: int

    def initialize(self, problem, budget, seed: int) -> InitialControl: ...
    def checkpoint(self, telemetry: dict, budget) -> SearchAction: ...
    def snapshot(self) -> dict: ...
    def close(self): ...


class WorkSlice:
    """A checkpoint allocation within one parent budget, never a fresh budget."""
    def __init__(self, parent, allocation):
        self.parent = parent
        self.end = min(parent.limit, parent.used + allocation)
        self.reason = None

    @property
    def used(self): return self.parent.used

    def check(self):
        if not self.parent.check():
            self.reason = self.parent.reason
        elif self.parent.used >= self.end:
            self.reason = 'checkpoint_budget'
        return self.reason is None

    def consume(self, category='search'):
        return self.check() and self.parent.consume(category)

    def require(self, category='construction'):
        from .budget import SearchStopped
        if not self.consume(category): raise SearchStopped(self.reason)
