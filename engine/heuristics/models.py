"""
Data models for the heuristic scoring system.

These models define the contract between the harness and heuristic functions.
"""

import numpy as np
from typing import List, Dict
from pydantic import BaseModel, Field, field_validator, ConfigDict


class HeuristicContext(BaseModel):
    """
    Input context provided to a scoring heuristic.
    
    The heuristic receives this immutable context and must return
    one score per candidate stop.
    
    Scoring Convention:
        Lower scores indicate better candidates (more preferred).
        The harness selects the candidate with the lowest score.
    
    Attributes:
        current_location: Index of current location (0=depot, 1..N=stops)
        candidate_stops: Indices of unvisited stops that need scoring
        distance_matrix: Full NxN distance matrix (read-only access)
        partial_route: Route constructed so far [depot, ..., current]
                      (read-only, for context only)
    
    Example:
        >>> ctx = HeuristicContext(
        ...     current_location=0,
        ...     candidate_stops=[1, 2, 3],
        ...     distance_matrix=np.array([[0, 10, 20, 30],
        ...                               [10, 0, 5, 15],
        ...                               [20, 5, 0, 10],
        ...                               [30, 15, 10, 0]]),
        ...     partial_route=[0]
        ... )
    """
    current_location: int = Field(..., ge=0, description="Current location index")
    candidate_stops: List[int] = Field(..., description="Unvisited stop indices")
    distance_matrix: np.ndarray = Field(..., description="Full distance matrix")
    partial_route: List[int] = Field(..., description="Route built so far")
    
    model_config = ConfigDict(arbitrary_types_allowed=True)
    
    @field_validator('candidate_stops')
    @classmethod
    def validate_candidates(cls, v: List[int]) -> List[int]:
        """Ensure candidate_stops is a list of unique positive integers."""
        if not all(isinstance(x, (int, np.integer)) and x > 0 for x in v):
            raise ValueError("All candidate stops must be positive integers")
        if len(v) != len(set(v)):
            raise ValueError("Candidate stops must be unique")
        return v
    
    @field_validator('partial_route')
    @classmethod
    def validate_partial_route(cls, v: List[int]) -> List[int]:
        """Ensure partial_route starts with depot."""
        if not v:
            raise ValueError("Partial route cannot be empty")
        if v[0] != 0:
            raise ValueError("Partial route must start with depot (0)")
        return v
    
    def __repr__(self) -> str:
        return (
            f"HeuristicContext(current={self.current_location}, "
            f"candidates={self.candidate_stops}, "
            f"partial_route={self.partial_route})"
        )


class HeuristicResult(BaseModel):
    """
    Output from a scoring heuristic.
    
    Must contain exactly one finite score per candidate stop.
    
    Attributes:
        scores: Dictionary mapping stop_index -> score
                Lower scores = more preferred candidates
                Must contain exactly the stops from HeuristicContext.candidate_stops
    
    Example:
        >>> result = HeuristicResult(scores={1: 10.0, 2: 20.0, 3: 30.0})
    """
    scores: Dict[int, float] = Field(..., description="Stop index -> score mapping")
    
    @field_validator('scores')
    @classmethod
    def validate_scores(cls, v: Dict[int, float]) -> Dict[int, float]:
        """Ensure all scores are finite numbers."""
        if not v:
            raise ValueError("Scores dictionary cannot be empty")
        
        for stop_id, score in v.items():
            # Validate stop ID
            if not isinstance(stop_id, (int, np.integer)) or stop_id <= 0:
                raise ValueError(f"Invalid stop ID {stop_id}: must be positive integer")
            
            # Validate score
            if not isinstance(score, (int, float, np.number)):
                raise ValueError(f"Score for stop {stop_id} must be numeric, got {type(score)}")
            
            if not np.isfinite(score):
                raise ValueError(f"Score for stop {stop_id} must be finite (not NaN or infinity)")
        
        return v
    
    def get_best_stop(self, candidate_stops: List[int]) -> int:
        """
        Get the candidate with the lowest score (deterministic tie-breaking).
        
        Args:
            candidate_stops: List of valid candidate stop indices
            
        Returns:
            Stop index with lowest score (ties broken by lowest index)
            
        Raises:
            ValueError: If scores don't match candidates
        """
        # Validate we have scores for all candidates
        if set(self.scores.keys()) != set(candidate_stops):
            missing = set(candidate_stops) - set(self.scores.keys())
            extra = set(self.scores.keys()) - set(candidate_stops)
            msg_parts = []
            if missing:
                msg_parts.append(f"missing scores for {sorted(missing)}")
            if extra:
                msg_parts.append(f"unexpected scores for {sorted(extra)}")
            raise ValueError(f"Score mismatch: {', '.join(msg_parts)}")
        
        # Find minimum score (deterministic tie-breaking: prefer lower index)
        best_stop = None
        best_score = float('inf')
        
        for stop in sorted(candidate_stops):  # Sort for deterministic tie-breaking
            score = self.scores[stop]
            if score < best_score or (score == best_score and stop < best_stop):
                best_stop = stop
                best_score = score
        
        return best_stop
    
    def __repr__(self) -> str:
        return f"HeuristicResult(scores={self.scores})"
