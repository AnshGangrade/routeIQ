"""Evolution package for LLM-guided heuristic discovery.

This package orchestrates the complete evolutionary loop:
- Configuration and instance generation
- Multiple generations with LLM feedback
- Candidate validation, evaluation, and selection
- Training/test split
- Result persistence and tracking
"""

from engine.evolution.config import EvolutionConfig
from engine.evolution.models import (
    CandidateRecord,
    GenerationRecord,
    EvolutionRun,
    BaselineComparison,
    TestSetEvaluation,
)
from engine.evolution.loop import EvolutionLoop
from engine.evolution.persistence import EvolutionPersistence

__all__ = [
    "EvolutionConfig",
    "CandidateRecord",
    "GenerationRecord",
    "EvolutionRun",
    "BaselineComparison",
    "TestSetEvaluation",
    "EvolutionLoop",
    "EvolutionPersistence",
]
