"""
Mock LLM mode for testing without API calls.

Returns predefined candidate heuristics without making network requests.
"""

from typing import Optional

from .models import GenerationRequest, LLMResponse, LLMConfig, LLMProvider


# Predefined mock candidates
MOCK_CANDIDATES = {
    "nearest_distance": """def score_candidates(context):
    \"\"\"Score by distance from current location (nearest neighbor).\"\"\"
    scores = {}
    for stop in context.candidate_stops:
        scores[stop] = context.distance_matrix[context.current_location, stop]
    return {"scores": scores}
""",
    
    "farthest_distance": """def score_candidates(context):
    \"\"\"Score by negative distance (farthest first - usually bad).\"\"\"
    scores = {}
    for stop in context.candidate_stops:
        # Negative distance means farthest gets lowest score
        scores[stop] = -context.distance_matrix[context.current_location, stop]
    return {"scores": scores}
""",
    
    "nearest_to_depot": """def score_candidates(context):
    \"\"\"Score by distance from depot (nearest to depot first).\"\"\"
    scores = {}
    depot = 0
    for stop in context.candidate_stops:
        scores[stop] = context.distance_matrix[depot, stop]
    return {"scores": scores}
""",
    
    "route_position_weighted": """def score_candidates(context):
    \"\"\"Score combining distance and route position.\"\"\"
    scores = {}
    route_length = len(context.partial_route)
    
    for stop in context.candidate_stops:
        distance = context.distance_matrix[context.current_location, stop]
        # Weight: favor nearby early in route, far later
        weight = 1.0 + 0.1 * route_length
        scores[stop] = distance * weight
    
    return {"scores": scores}
""",
    
    "centroid_based": """def score_candidates(context):
    \"\"\"Score by distance to centroid of remaining candidates.\"\"\"
    import numpy as np
    
    scores = {}
    
    # Calculate centroid of all candidate stops
    if len(context.candidate_stops) > 1:
        candidate_positions = [context.distance_matrix[0, stop] for stop in context.candidate_stops]
        centroid_dist = sum(candidate_positions) / len(candidate_positions)
    else:
        centroid_dist = 0
    
    for stop in context.candidate_stops:
        # Score by distance from current plus deviation from centroid
        direct_dist = context.distance_matrix[context.current_location, stop]
        depot_dist = context.distance_matrix[0, stop]
        centroid_deviation = abs(depot_dist - centroid_dist)
        
        scores[stop] = direct_dist + 0.2 * centroid_deviation
    
    return {"scores": scores}
""",
    
    "invalid_import": """import os

def score_candidates(context):
    \"\"\"Invalid: contains import statement.\"\"\"
    scores = {}
    for stop in context.candidate_stops:
        scores[stop] = context.distance_matrix[context.current_location, stop]
    return {"scores": scores}
""",
    
    "invalid_open": """def score_candidates(context):
    \"\"\"Invalid: attempts file I/O.\"\"\"
    with open("/tmp/log.txt", "w") as f:
        f.write("hacking the system")
    
    scores = {}
    for stop in context.candidate_stops:
        scores[stop] = context.distance_matrix[context.current_location, stop]
    return {"scores": scores}
""",
    
    "invalid_syntax": """def score_candidates(context):
    \"\"\"Invalid: syntax error.\"\"\"
    scores = {
    for stop in context.candidate_stops:
        scores[stop] = context.distance_matrix[context.current_location, stop]
    return {"scores": scores}
""",
}


class MockLLMClient:
    """
    Mock LLM client that returns predefined candidates.
    
    Useful for:
    - Testing without API calls
    - Demos without API keys
    - Deterministic testing of validation and evaluation
    
    Usage:
        >>> config = LLMConfig(
        ...     provider=LLMProvider.MOCK,
        ...     base_url="mock://local",
        ...     model="mock-v1"
        ... )
        >>> client = MockLLMClient(config)
        >>> request = GenerationRequest(
        ...     prompt="any prompt",
        ...     metadata={"candidate_key": "nearest_distance"}
        ... )
        >>> response = client.generate(request)
    """
    
    def __init__(self, config: LLMConfig):
        """
        Initialize mock client.
        
        Args:
            config: LLM configuration (must have provider=MOCK)
        """
        if config.provider != LLMProvider.MOCK:
            raise ValueError(f"MockLLMClient requires provider=MOCK, got {config.provider}")
        
        self.config = config
        self._call_count = 0
    
    def generate(self, request: GenerationRequest) -> LLMResponse:
        """
        Generate a mock response.
        
        Candidate selection:
        1. If request.metadata["candidate_key"] is set, use that candidate
        2. Otherwise cycle through candidates based on call count
        
        Args:
            request: Generation request
            
        Returns:
            LLM response with predefined candidate
        """
        self._call_count += 1
        
        # Check if specific candidate requested
        candidate_key = request.metadata.get("candidate_key")
        
        if candidate_key:
            if candidate_key not in MOCK_CANDIDATES:
                raise ValueError(
                    f"Unknown mock candidate '{candidate_key}'. "
                    f"Available: {list(MOCK_CANDIDATES.keys())}"
                )
            source_code = MOCK_CANDIDATES[candidate_key]
        else:
            # Cycle through candidates
            candidate_keys = list(MOCK_CANDIDATES.keys())
            # Only cycle through valid candidates by default
            valid_keys = [k for k in candidate_keys if not k.startswith("invalid_")]
            
            index = (self._call_count - 1) % len(valid_keys)
            candidate_key = valid_keys[index]
            source_code = MOCK_CANDIDATES[candidate_key]
        
        # Build response
        metadata = {
            "mock_candidate": candidate_key,
            "call_count": self._call_count,
            "mode": "mock",
        }
        metadata.update(request.metadata)
        
        return LLMResponse(
            raw_content=source_code,
            provider="mock",
            model=self.config.model,
            generation_id=request.generation_id,
            metadata=metadata
        )
    
    def close(self):
        """No-op for mock client."""
        pass
    
    def __enter__(self):
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
    
    def __repr__(self) -> str:
        return f"MockLLMClient(calls={self._call_count})"


def get_mock_candidate(key: str) -> str:
    """
    Get a mock candidate by key.
    
    Args:
        key: Candidate key (e.g., "nearest_distance", "invalid_import")
        
    Returns:
        Source code string
        
    Raises:
        KeyError: If key not found
    """
    return MOCK_CANDIDATES[key]


def list_mock_candidates() -> list[str]:
    """
    List available mock candidate keys.
    
    Returns:
        List of candidate keys
    """
    return list(MOCK_CANDIDATES.keys())
