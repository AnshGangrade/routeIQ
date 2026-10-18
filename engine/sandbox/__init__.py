"""
Validation and controlled execution of candidate heuristics.

This module provides safety layers for executing untrusted LLM-generated code:
- Static AST validation (allowlist-based Python subset)
- Controlled execution with restricted namespace
- Timeout enforcement
- Structured error reporting

Security Note:
    This is defense-in-depth for an academic demo, NOT a security boundary.
    Do not use this to execute truly malicious code or run on public servers.
"""

from .models import CandidateHeuristic, ValidationResult, ExecutionResult
from .validator import HeuristicValidator
from .executor import HeuristicExecutor
from .adapter import CandidateAdapter, create_scoring_function

__all__ = [
    "CandidateHeuristic",
    "ValidationResult",
    "ExecutionResult",
    "HeuristicValidator",
    "HeuristicExecutor",
    "CandidateAdapter",
    "create_scoring_function",
]
