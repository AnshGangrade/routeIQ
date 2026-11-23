"""
Replay LLM mode for testing with saved responses.

Loads responses from fixture files without making network requests.
"""

import json
from pathlib import Path
from typing import Dict, Any, Optional

from .models import GenerationRequest, LLMResponse, LLMConfig, LLMProvider


class ReplayLLMClient:
    """
    Replay LLM client that loads responses from saved fixtures.
    
    Useful for:
    - Testing with real LLM outputs without API calls
    - Deterministic test runs
    - Development without API credits
    
    Fixture format (JSON):
    {
        "generation_id": "optional_id",
        "raw_content": "def score_candidates(context): ...",
        "provider": "openai",
        "model": "gpt-4",
        "metadata": {}
    }
    
    Usage:
        >>> config = LLMConfig(
        ...     provider=LLMProvider.REPLAY,
        ...     base_url="replay://local",
        ...     model="replay-v1"
        ... )
        >>> client = ReplayLLMClient(config, fixture_dir="tests/fixtures/llm_responses")
        >>> request = GenerationRequest(
        ...     prompt="any prompt",
        ...     generation_id="test_case_1"
        ... )
        >>> response = client.generate(request)
    """
    
    def __init__(self, config: LLMConfig, fixture_dir: Optional[str] = None):
        """
        Initialize replay client.
        
        Args:
            config: LLM configuration (must have provider=REPLAY)
            fixture_dir: Directory containing fixture files (default: tests/fixtures/llm_responses)
        """
        if config.provider != LLMProvider.REPLAY:
            raise ValueError(f"ReplayLLMClient requires provider=REPLAY, got {config.provider}")
        
        self.config = config
        
        # Default fixture directory
        if fixture_dir is None:
            fixture_dir = Path(__file__).parent.parent.parent / "tests" / "fixtures" / "llm_responses"
        else:
            fixture_dir = Path(fixture_dir)
        
        self.fixture_dir = fixture_dir
        self._call_count = 0
        self._cache: Dict[str, LLMResponse] = {}
    
    def _load_fixture(self, fixture_name: str) -> LLMResponse:
        """
        Load a fixture file.
        
        Args:
            fixture_name: Fixture filename (with or without .json extension)
            
        Returns:
            LLM response
            
        Raises:
            FileNotFoundError: If fixture file doesn't exist
            ValueError: If fixture format is invalid
        """
        # Check cache
        if fixture_name in self._cache:
            return self._cache[fixture_name]
        
        # Add .json extension if not present
        if not fixture_name.endswith(".json"):
            fixture_name = f"{fixture_name}.json"
        
        fixture_path = self.fixture_dir / fixture_name
        
        if not fixture_path.exists():
            raise FileNotFoundError(
                f"Fixture not found: {fixture_path}\n"
                f"Available fixtures: {self.list_fixtures()}"
            )
        
        # Load fixture
        try:
            with open(fixture_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in fixture {fixture_name}: {e}") from e
        
        # Parse into LLMResponse
        try:
            response = LLMResponse(**data)
        except Exception as e:
            raise ValueError(f"Invalid fixture format in {fixture_name}: {e}") from e
        
        # Cache and return
        self._cache[fixture_name] = response
        return response
    
    def generate(self, request: GenerationRequest) -> LLMResponse:
        """
        Generate a response by loading from fixture.
        
        Fixture selection:
        1. Use request.metadata["fixture_name"] when explicitly supplied
        2. Cycle the configured replay_fixtures sequence, when present
        3. Otherwise load the fixture named by request.generation_id
        4. Raise an error if no fixture identifier is available
        
        Args:
            request: Generation request
            
        Returns:
            LLM response loaded from fixture
            
        Raises:
            ValueError: If no fixture identifier provided
            FileNotFoundError: If fixture doesn't exist
        """
        self._call_count += 1
        
        # Determine fixture name
        fixture_name = None
        
        if "fixture_name" in request.metadata:
            fixture_name = request.metadata["fixture_name"]
        elif self.config.replay_fixtures:
            fixture_name = self.config.replay_fixtures[(self._call_count - 1) % len(self.config.replay_fixtures)]
        elif request.generation_id:
            fixture_name = request.generation_id
        
        if not fixture_name:
            raise ValueError(
                "Replay mode requires either request.generation_id or "
                "request.metadata['fixture_name'] to identify the fixture. "
                f"Available fixtures: {self.list_fixtures()}"
            )
        
        # Load fixture
        response = self._load_fixture(fixture_name).model_copy(deep=True)
        
        # Update metadata
        response.metadata["mode"] = "replay"
        response.metadata["call_count"] = self._call_count
        response.metadata["fixture_name"] = fixture_name
        
        # Override generation_id if provided
        if request.generation_id:
            response.generation_id = request.generation_id
        
        return response
    
    def list_fixtures(self) -> list[str]:
        """
        List available fixture files.
        
        Returns:
            List of fixture names (without .json extension)
        """
        if not self.fixture_dir.exists():
            return []
        
        fixtures = []
        for path in self.fixture_dir.glob("*.json"):
            fixtures.append(path.stem)
        
        return sorted(fixtures)
    
    def close(self):
        """No-op for replay client."""
        pass
    
    def __enter__(self):
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
    
    def __repr__(self) -> str:
        return f"ReplayLLMClient(fixture_dir={self.fixture_dir}, calls={self._call_count})"


def save_response_as_fixture(
    response: LLMResponse,
    fixture_name: str,
    fixture_dir: Optional[str] = None
) -> Path:
    """
    Save an LLM response as a fixture file.
    
    Useful for capturing real API responses for replay testing.
    
    Args:
        response: LLM response to save
        fixture_name: Fixture filename (without .json extension)
        fixture_dir: Directory to save in (default: tests/fixtures/llm_responses)
        
    Returns:
        Path to saved fixture file
    """
    # Default fixture directory
    if fixture_dir is None:
        fixture_dir = Path(__file__).parent.parent.parent / "tests" / "fixtures" / "llm_responses"
    else:
        fixture_dir = Path(fixture_dir)
    
    # Create directory if needed
    fixture_dir.mkdir(parents=True, exist_ok=True)
    
    # Add .json extension if not present
    if not fixture_name.endswith(".json"):
        fixture_name = f"{fixture_name}.json"
    
    fixture_path = fixture_dir / fixture_name
    
    # Save fixture
    with open(fixture_path, 'w', encoding='utf-8') as f:
        json.dump(response.model_dump(), f, indent=2, ensure_ascii=False)
    
    return fixture_path
