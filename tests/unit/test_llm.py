"""
Unit tests for LLM integration module.

Tests all LLM components without making live API calls.
"""

import pytest
import json
from pathlib import Path

from engine.llm import (
    LLMProvider,
    LLMConfig,
    GenerationRequest,
    LLMResponse,
    ParseResult,
    MockLLMClient,
    ReplayLLMClient,
    create_client,
    build_generation_prompt,
    build_feedback_prompt,
    build_refinement_prompt,
    parse_llm_response,
    extract_code_blocks,
    extract_function_name,
    get_mock_candidate,
    list_mock_candidates,
    save_response_as_fixture,
)


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def mock_config():
    """Mock LLM configuration."""
    return LLMConfig(
        provider=LLMProvider.MOCK,
        base_url="mock://local",
        model="mock-v1",
        temperature=0.7
    )


@pytest.fixture
def replay_config():
    """Replay LLM configuration."""
    return LLMConfig(
        provider=LLMProvider.REPLAY,
        base_url="replay://local",
        model="replay-v1",
        temperature=0.7
    )


@pytest.fixture
def fixture_dir():
    """Fixture directory path."""
    return Path(__file__).parent.parent / "fixtures" / "llm_responses"


# ============================================================================
# Model Tests
# ============================================================================

class TestLLMConfig:
    """Test LLM configuration model."""
    
    def test_create_config(self):
        """Test creating LLM config."""
        config = LLMConfig(
            provider=LLMProvider.OPENAI,
            api_key="sk-test",
            base_url="https://api.openai.com/v1",
            model="gpt-4",
            temperature=0.7
        )
        
        assert config.provider == LLMProvider.OPENAI
        assert config.api_key == "sk-test"
        assert config.model == "gpt-4"
        assert config.temperature == 0.7
    
    def test_config_repr_hides_key(self):
        """Test that config repr doesn't leak API key."""
        config = LLMConfig(
            provider=LLMProvider.OPENAI,
            api_key="sk-secret-key-12345",
            base_url="https://api.openai.com/v1",
            model="gpt-4"
        )
        
        repr_str = repr(config)
        assert "sk-secret" not in repr_str
        assert "12345" not in repr_str
        assert "***" in repr_str or "set" in repr_str
    
    def test_config_temperature_validation(self):
        """Test temperature validation."""
        # Valid temperatures
        LLMConfig(
            provider=LLMProvider.MOCK,
            base_url="mock://",
            model="test",
            temperature=0.0
        )
        LLMConfig(
            provider=LLMProvider.MOCK,
            base_url="mock://",
            model="test",
            temperature=1.0
        )
        
        # Invalid temperatures
        with pytest.raises(ValueError):
            LLMConfig(
                provider=LLMProvider.MOCK,
                base_url="mock://",
                model="test",
                temperature=-0.1
            )
        
        with pytest.raises(ValueError):
            LLMConfig(
                provider=LLMProvider.MOCK,
                base_url="mock://",
                model="test",
                temperature=1.1
            )


class TestGenerationRequest:
    """Test generation request model."""
    
    def test_create_request(self):
        """Test creating generation request."""
        request = GenerationRequest(
            prompt="Generate a heuristic",
            generation_id="test_001",
            metadata={"iteration": 1}
        )
        
        assert request.prompt == "Generate a heuristic"
        assert request.generation_id == "test_001"
        assert request.metadata["iteration"] == 1


class TestLLMResponse:
    """Test LLM response model."""
    
    def test_create_response(self):
        """Test creating LLM response."""
        response = LLMResponse(
            raw_content="def score_candidates(context): pass",
            provider="openai",
            model="gpt-4",
            generation_id="test_001",
            metadata={"latency_seconds": 1.5}
        )
        
        assert "def score_candidates" in response.raw_content
        assert response.provider == "openai"
        assert response.model == "gpt-4"


# ============================================================================
# Prompt Builder Tests
# ============================================================================

class TestPromptBuilders:
    """Test prompt building functions."""
    
    def test_build_generation_prompt_initial(self):
        """Test building initial generation prompt."""
        prompt = build_generation_prompt(iteration=0)
        
        # Check key components
        assert "score_candidates" in prompt
        assert "def score_candidates(context):" in prompt
        assert "LOWER scores = MORE preferred" in prompt
        assert "NO imports" in prompt
        assert "distance_matrix" in prompt
    
    def test_build_generation_prompt_with_feedback(self):
        """Test building prompt with feedback."""
        prompt = build_generation_prompt(
            iteration=2,
            feedback="Try considering route position",
            best_score=150.5,
            context={"num_stops": 20, "num_drivers": 3}
        )
        
        assert "Iteration 2" in prompt
        assert "150.5" in prompt
        assert "route position" in prompt
        assert "20 delivery stops" in prompt
        assert "3" in prompt and "drivers" in prompt
    
    def test_build_feedback_prompt(self):
        """Test building feedback prompt."""
        feedback = build_feedback_prompt(
            fitness_score=125.0,
            comparison="10% better than nearest neighbor",
            suggestions="Consider depot proximity"
        )
        
        assert "125.0" in feedback
        assert "10% better" in feedback
        assert "depot proximity" in feedback
    
    def test_build_refinement_prompt(self):
        """Test building refinement prompt."""
        source = "def score_candidates(context):\n    return {'scores': {}}"
        feedback = "Add distance consideration"
        
        prompt = build_refinement_prompt(source, feedback)
        
        assert "def score_candidates" in prompt
        assert "distance consideration" in prompt
        assert "IMPROVED version" in prompt


# ============================================================================
# Parser Tests
# ============================================================================

class TestCodeExtraction:
    """Test code extraction from responses."""
    
    def test_extract_fenced_code(self):
        """Test extracting fenced code blocks."""
        text = """Here's the function:
```python
def score_candidates(context):
    return {"scores": {}}
```
That should work!"""
        
        blocks = extract_code_blocks(text)
        assert len(blocks) == 1
        assert "def score_candidates" in blocks[0]
    
    def test_extract_unfenced_code(self):
        """Test extracting unfenced code."""
        text = "def score_candidates(context):\n    return {'scores': {}}"
        
        blocks = extract_code_blocks(text)
        assert len(blocks) == 1
        assert "def score_candidates" in blocks[0]
    
    def test_extract_multiple_blocks(self):
        """Test extracting multiple code blocks."""
        text = """First attempt:
```python
def foo(): pass
```

Better version:
```python
def bar(): pass
```"""
        
        blocks = extract_code_blocks(text)
        assert len(blocks) == 2
    
    def test_extract_function_name(self):
        """Test extracting function name."""
        code = "def score_candidates(context):\n    pass"
        
        name = extract_function_name(code)
        assert name == "score_candidates"
    
    def test_extract_function_name_multiple(self):
        """Test extracting from code with multiple functions."""
        code = """
def helper():
    pass

def score_candidates(context):
    pass
"""
        
        # Should prefer score_candidates
        name = extract_function_name(code)
        assert name == "score_candidates"
    
    def test_extract_function_name_syntax_error(self):
        """Test extracting from invalid syntax."""
        code = "def broken(:\n    pass"
        
        name = extract_function_name(code)
        assert name is None


class TestResponseParsing:
    """Test LLM response parsing."""
    
    def test_parse_valid_response(self):
        """Test parsing valid response."""
        response = LLMResponse(
            raw_content="""```python
def score_candidates(context):
    scores = {}
    for stop in context.candidate_stops:
        scores[stop] = context.distance_matrix[context.current_location, stop]
    return {"scores": scores}
```""",
            provider="test",
            model="test"
        )
        
        result = parse_llm_response(response)
        
        assert result.success
        assert result.function_name == "score_candidates"
        assert "def score_candidates" in result.source_code
        assert len(result.errors) == 0
    
    def test_parse_response_without_fences(self):
        """Test parsing response without code fences."""
        response = LLMResponse(
            raw_content='def score_candidates(context):\n    return {"scores": {}}',
            provider="test",
            model="test"
        )
        
        result = parse_llm_response(response)
        
        assert result.success
        assert result.function_name == "score_candidates"
    
    def test_parse_response_with_imports(self):
        """Test parsing response with prohibited imports."""
        response = LLMResponse(
            raw_content="""import os

def score_candidates(context):
    return {"scores": {}}
""",
            provider="test",
            model="test"
        )
        
        result = parse_llm_response(response)
        
        assert not result.success
        assert any("import" in err.lower() for err in result.errors)
    
    def test_parse_response_with_open(self):
        """Test parsing response with file I/O."""
        response = LLMResponse(
            raw_content="""def score_candidates(context):
    with open('/tmp/log.txt', 'w') as f:
        f.write('test')
    return {"scores": {}}
""",
            provider="test",
            model="test"
        )
        
        result = parse_llm_response(response)
        
        assert not result.success
        assert any("open()" in err for err in result.errors)
    
    def test_parse_response_syntax_error(self):
        """Test parsing response with syntax error."""
        response = LLMResponse(
            raw_content="def score_candidates(context):\n    return {",
            provider="test",
            model="test"
        )
        
        result = parse_llm_response(response)
        
        assert not result.success
        assert any("syntax error" in err.lower() for err in result.errors)
    
    def test_parse_response_no_code(self):
        """Test parsing response without code."""
        response = LLMResponse(
            raw_content="I think you should use a greedy approach.",
            provider="test",
            model="test"
        )
        
        result = parse_llm_response(response)
        
        assert not result.success
        # Parser should fail with either "no code found" or "no function definition found"
        assert len(result.errors) > 0


# ============================================================================
# Mock Client Tests
# ============================================================================

class TestMockLLMClient:
    """Test mock LLM client."""
    
    def test_create_mock_client(self, mock_config):
        """Test creating mock client."""
        client = MockLLMClient(mock_config)
        assert client.config.provider == LLMProvider.MOCK
    
    def test_mock_client_requires_mock_provider(self):
        """Test that mock client requires MOCK provider."""
        config = LLMConfig(
            provider=LLMProvider.OPENAI,
            api_key="test",
            base_url="https://api.openai.com/v1",
            model="gpt-4"
        )
        
        with pytest.raises(ValueError, match="requires provider=MOCK"):
            MockLLMClient(config)
    
    def test_mock_generate_default(self, mock_config):
        """Test mock generation with default cycling."""
        client = MockLLMClient(mock_config)
        
        request = GenerationRequest(prompt="test")
        response = client.generate(request)
        
        assert response.raw_content
        assert response.provider == "mock"
        assert "def score_candidates" in response.raw_content
    
    def test_mock_generate_specific_candidate(self, mock_config):
        """Test mock generation with specific candidate."""
        client = MockLLMClient(mock_config)
        
        request = GenerationRequest(
            prompt="test",
            metadata={"candidate_key": "nearest_distance"}
        )
        response = client.generate(request)
        
        assert "nearest neighbor" in response.raw_content.lower()
        assert response.metadata["mock_candidate"] == "nearest_distance"
    
    def test_mock_generate_invalid_candidate(self, mock_config):
        """Test mock generation with invalid candidate key."""
        client = MockLLMClient(mock_config)
        
        request = GenerationRequest(
            prompt="test",
            metadata={"candidate_key": "nonexistent"}
        )
        
        with pytest.raises(ValueError, match="Unknown mock candidate"):
            client.generate(request)
    
    def test_mock_cycling(self, mock_config):
        """Test that mock client cycles through candidates."""
        client = MockLLMClient(mock_config)
        
        responses = []
        for _ in range(3):
            request = GenerationRequest(prompt="test")
            response = client.generate(request)
            responses.append(response.metadata["mock_candidate"])
        
        # Should cycle through different candidates
        assert len(set(responses)) >= 2
    
    def test_mock_context_manager(self, mock_config):
        """Test mock client as context manager."""
        with MockLLMClient(mock_config) as client:
            request = GenerationRequest(prompt="test")
            response = client.generate(request)
            assert response.provider == "mock"
    
    def test_list_mock_candidates(self):
        """Test listing mock candidates."""
        candidates = list_mock_candidates()
        
        assert "nearest_distance" in candidates
        assert "invalid_import" in candidates
        assert len(candidates) > 3
    
    def test_get_mock_candidate(self):
        """Test getting specific mock candidate."""
        code = get_mock_candidate("nearest_distance")
        
        assert "def score_candidates" in code
        assert "distance_matrix" in code


# ============================================================================
# Replay Client Tests
# ============================================================================

class TestReplayLLMClient:
    """Test replay LLM client."""
    
    def test_create_replay_client(self, replay_config, fixture_dir):
        """Test creating replay client."""
        client = ReplayLLMClient(replay_config, fixture_dir=str(fixture_dir))
        assert client.config.provider == LLMProvider.REPLAY
    
    def test_replay_client_requires_replay_provider(self, fixture_dir):
        """Test that replay client requires REPLAY provider."""
        config = LLMConfig(
            provider=LLMProvider.OPENAI,
            api_key="test",
            base_url="https://api.openai.com/v1",
            model="gpt-4"
        )
        
        with pytest.raises(ValueError, match="requires provider=REPLAY"):
            ReplayLLMClient(config, fixture_dir=str(fixture_dir))
    
    def test_replay_generate_with_generation_id(self, replay_config, fixture_dir):
        """Test replay generation using generation_id."""
        client = ReplayLLMClient(replay_config, fixture_dir=str(fixture_dir))
        
        request = GenerationRequest(
            prompt="test",
            generation_id="simple_nearest"
        )
        response = client.generate(request)
        
        assert "def score_candidates" in response.raw_content
        assert response.metadata["mode"] == "replay"
    
    def test_replay_generate_with_fixture_name(self, replay_config, fixture_dir):
        """Test replay generation using fixture_name metadata."""
        client = ReplayLLMClient(replay_config, fixture_dir=str(fixture_dir))
        
        request = GenerationRequest(
            prompt="test",
            metadata={"fixture_name": "weighted_heuristic"}
        )
        response = client.generate(request)
        
        assert "route_progress" in response.raw_content
    
    def test_replay_generate_missing_identifier(self, replay_config, fixture_dir):
        """Test replay generation without identifier."""
        client = ReplayLLMClient(replay_config, fixture_dir=str(fixture_dir))
        
        request = GenerationRequest(prompt="test")
        
        with pytest.raises(ValueError, match="requires either request.generation_id"):
            client.generate(request)
    
    def test_replay_generate_nonexistent_fixture(self, replay_config, fixture_dir):
        """Test replay generation with nonexistent fixture."""
        client = ReplayLLMClient(replay_config, fixture_dir=str(fixture_dir))
        
        request = GenerationRequest(
            prompt="test",
            generation_id="does_not_exist"
        )
        
        with pytest.raises(FileNotFoundError, match="Fixture not found"):
            client.generate(request)
    
    def test_replay_list_fixtures(self, replay_config, fixture_dir):
        """Test listing available fixtures."""
        client = ReplayLLMClient(replay_config, fixture_dir=str(fixture_dir))
        
        fixtures = client.list_fixtures()
        
        assert "simple_nearest" in fixtures
        assert "weighted_heuristic" in fixtures
        assert "malformed_response" in fixtures
    
    def test_replay_caching(self, replay_config, fixture_dir):
        """Test that replay client caches fixtures."""
        client = ReplayLLMClient(replay_config, fixture_dir=str(fixture_dir))
        
        # Load same fixture twice
        request1 = GenerationRequest(
            prompt="test",
            generation_id="simple_nearest"
        )
        response1 = client.generate(request1)
        
        request2 = GenerationRequest(
            prompt="test",
            generation_id="simple_nearest"
        )
        response2 = client.generate(request2)
        
        # Should return same content
        assert response1.raw_content == response2.raw_content
    
    def test_replay_context_manager(self, replay_config, fixture_dir):
        """Test replay client as context manager."""
        with ReplayLLMClient(replay_config, fixture_dir=str(fixture_dir)) as client:
            request = GenerationRequest(
                prompt="test",
                generation_id="simple_nearest"
            )
            response = client.generate(request)
            assert response.metadata["mode"] == "replay"


class TestSaveFixture:
    """Test saving responses as fixtures."""
    
    def test_save_response_as_fixture(self, tmp_path):
        """Test saving a response as fixture."""
        response = LLMResponse(
            raw_content="def test(): pass",
            provider="test",
            model="test-model",
            generation_id="test_save",
            metadata={"test": True}
        )
        
        fixture_path = save_response_as_fixture(
            response,
            fixture_name="test_fixture",
            fixture_dir=str(tmp_path)
        )
        
        assert fixture_path.exists()
        assert fixture_path.suffix == ".json"
        
        # Verify content
        with open(fixture_path, 'r') as f:
            data = json.load(f)
        
        assert data["raw_content"] == "def test(): pass"
        assert data["provider"] == "test"


# ============================================================================
# Integration Tests
# ============================================================================

class TestClientFactory:
    """Test client factory function."""
    
    def test_create_mock_client(self, mock_config):
        """Test creating mock client via factory."""
        client = create_client(mock_config)
        assert isinstance(client, MockLLMClient)
    
    def test_create_replay_client(self, replay_config):
        """Test creating replay client via factory."""
        client = create_client(replay_config)
        assert isinstance(client, ReplayLLMClient)


class TestEndToEndMock:
    """End-to-end test with mock client."""
    
    def test_generate_parse_validate_cycle(self, mock_config):
        """Test complete cycle: generate -> parse -> validate."""
        from engine.sandbox import HeuristicValidator, CandidateHeuristic
        
        # Generate
        with create_client(mock_config) as client:
            request = GenerationRequest(
                prompt="test",
                metadata={"candidate_key": "nearest_distance"}
            )
            response = client.generate(request)
        
        # Parse
        parse_result = parse_llm_response(response)
        assert parse_result.success
        
        # Create candidate
        candidate = CandidateHeuristic(
            source_code=parse_result.source_code,
            function_name=parse_result.function_name
        )
        
        # Validate (using M4 validator)
        validator = HeuristicValidator()
        validation_result = validator.validate(candidate)
        
        assert validation_result.is_valid


class TestEndToEndReplay:
    """End-to-end test with replay client."""
    
    def test_generate_parse_from_fixture(self, replay_config, fixture_dir):
        """Test generating and parsing from fixture."""
        # Generate
        with ReplayLLMClient(replay_config, fixture_dir=str(fixture_dir)) as client:
            request = GenerationRequest(
                prompt="test",
                generation_id="simple_nearest"
            )
            response = client.generate(request)
        
        # Parse
        parse_result = parse_llm_response(response)
        
        assert parse_result.success
        assert parse_result.function_name == "score_candidates"
    
    def test_parse_malformed_fixture(self, replay_config, fixture_dir):
        """Test parsing malformed response from fixture."""
        # Generate
        with ReplayLLMClient(replay_config, fixture_dir=str(fixture_dir)) as client:
            request = GenerationRequest(
                prompt="test",
                generation_id="malformed_response"
            )
            response = client.generate(request)
        
        # Parse (should fail gracefully)
        parse_result = parse_llm_response(response)
        
        assert not parse_result.success
        assert len(parse_result.errors) > 0
