"""
Data models for candidate heuristic validation and execution.
"""

from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from enum import Enum


class ValidationStatus(str, Enum):
    """Status of candidate validation."""
    VALID = "valid"
    INVALID = "invalid"


class ExecutionStatus(str, Enum):
    """Status of candidate execution."""
    SUCCESS = "success"
    SYNTAX_ERROR = "syntax_error"
    RUNTIME_ERROR = "runtime_error"
    TIMEOUT = "timeout"
    INVALID_OUTPUT = "invalid_output"


class CandidateHeuristic(BaseModel):
    """
    A candidate heuristic function for validation and execution.
    
    This represents untrusted LLM-generated code that must be validated
    before execution.
    
    Attributes:
        source_code: Python source code as string
        function_name: Name of the entry point function (default: "score_candidates")
        metadata: Optional metadata (generation parameters, etc.)
    
    Example:
        >>> candidate = CandidateHeuristic(
        ...     source_code='''
        ... def score_candidates(context):
        ...     scores = {}
        ...     for stop in context.candidate_stops:
        ...         scores[stop] = context.distance_matrix[context.current_location, stop]
        ...     return {"scores": scores}
        ... ''',
        ...     function_name="score_candidates"
        ... )
    """
    source_code: str = Field(..., description="Python source code")
    function_name: str = Field(default="score_candidates", description="Entry point function name")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Optional metadata")
    
    def __repr__(self) -> str:
        lines = self.source_code.count('\n') + 1
        return f"CandidateHeuristic(function={self.function_name}, lines={lines})"


class ValidationResult(BaseModel):
    """
    Result of static validation.
    
    Attributes:
        status: VALID or INVALID
        errors: List of validation error messages
        warnings: List of validation warnings (non-blocking)
        details: Additional validation details
    """
    status: ValidationStatus
    errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    details: Dict[str, Any] = Field(default_factory=dict)
    
    @property
    def is_valid(self) -> bool:
        """Check if validation passed."""
        return self.status == ValidationStatus.VALID
    
    def __repr__(self) -> str:
        if self.is_valid:
            return f"ValidationResult(VALID, warnings={len(self.warnings)})"
        return f"ValidationResult(INVALID, errors={len(self.errors)})"


class ExecutionResult(BaseModel):
    """
    Result of heuristic execution.
    
    Attributes:
        status: Execution status (success, error, timeout, etc.)
        output: Returned value if successful
        error: Error message if failed
        execution_time: Time taken in seconds
        details: Additional execution details
    """
    status: ExecutionStatus
    output: Optional[Any] = None
    error: Optional[str] = None
    execution_time: Optional[float] = None
    details: Dict[str, Any] = Field(default_factory=dict)
    
    @property
    def is_success(self) -> bool:
        """Check if execution succeeded."""
        return self.status == ExecutionStatus.SUCCESS
    
    def __repr__(self) -> str:
        if self.is_success:
            return f"ExecutionResult(SUCCESS, time={self.execution_time:.3f}s)"
        return f"ExecutionResult({self.status.value.upper()}, error={self.error})"
