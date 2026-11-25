"""Finite controller actions around the existing fleet-strategy/v1 schema."""
from typing import Literal
from pydantic import Field, model_validator
from .models import StrictModel, StrategyConfig
from .provider import ProviderConfig

Operator = Literal['relocate','swap','or_opt_2','two_opt','cross_relocate','cross_exchange']


class AdaptiveLimits(StrictModel):
    max_calls: int = Field(4, strict=True, ge=1, le=8)
    max_checkpoints: int = Field(4, strict=True, ge=1, le=8)
    max_model_seconds: float = Field(15., gt=0, le=30)
    context_tokens: int = Field(8192, strict=True, ge=4096, le=8192)
    max_reserved_tokens: int = Field(40000, strict=True, ge=4608, le=100000)
    max_prompt_bytes: int = Field(24000, strict=True, ge=4096, le=32000)


class AdaptiveRequest(StrictModel):
    provider: ProviderConfig = ProviderConfig(model='qwen3:1.7b',timeout=5,retries=0,max_tokens=768)
    limits: AdaptiveLimits = AdaptiveLimits()
    experience_job_ids: tuple[str, ...] = Field((), max_length=3)

    @model_validator(mode='after')
    def bounded(self):
        if self.provider.retries != 0:
            raise ValueError('Adaptive calls use zero retries; each checkpoint has one request')
        if self.provider.max_tokens > 2048 or self.provider.timeout > 10:
            raise ValueError('Adaptive provider allows at most 2048 output tokens and 10 seconds per request')
        if self.limits.max_reserved_tokens < self.limits.context_tokens + self.provider.max_tokens:
            raise ValueError('Token allowance must cover the initial request')
        return self


class InitialSelection(StrictModel):
    config: StrategyConfig
    operation_slice: int = Field(10000, strict=True, ge=100, le=20000)
    rationale: str = Field('', max_length=500)


class AdaptiveAction(StrictModel):
    action: Literal['continue','reorder','diversify','stop']
    operators: tuple[Operator, ...] = ()
    max_moves: int | None = Field(None, strict=True, ge=1, le=100000)
    operation_slice: int = Field(10000, strict=True, ge=100, le=20000)
    rationale: str = Field('', max_length=500)

    @model_validator(mode='after')
    def scheduling(self):
        if len(set(self.operators)) != len(self.operators): raise ValueError('Duplicate operators')
        if (self.action == 'reorder') != bool(self.operators):
            raise ValueError('Only reorder supplies a nonempty ordered operator subset')
        return self
