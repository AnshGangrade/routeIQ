"""
LLM integration for heuristic generation.

This module provides the runtime LLM client for generating candidate heuristics.
It is completely separate from Kiro's development model.

Components:
- LLMClient: HTTP client for OpenAI-compatible APIs
- MockLLMClient: Testing without API calls
- ReplayLLMClient: Load from saved fixtures
- Prompt builders: Generate prompts for heuristic generation
- Response parser: Extract code from LLM responses

Usage:
    >>> from engine.llm import load_config_from_env, create_client, GenerationRequest
    >>> from engine.llm import build_generation_prompt, parse_llm_response
    >>> 
    >>> # Load configuration from .env
    >>> config = load_config_from_env()
    >>> 
    >>> # Create client (auto-selects mock/replay/live based on config)
    >>> with create_client(config) as client:
    >>>     # Build prompt
    >>>     prompt = build_generation_prompt(iteration=0)
    >>>     
    >>>     # Generate
    >>>     request = GenerationRequest(prompt=prompt, generation_id="gen_001")
    >>>     response = client.generate(request)
    >>>     
    >>>     # Parse
    >>>     result = parse_llm_response(response)
    >>>     if result.success:
    >>>         print(f"Extracted {result.function_name}")
"""

from .models import (
    LLMProvider,
    LLMConfig,
    GenerationRequest,
    LLMResponse,
    ParseResult,
)

from .client import (
    LLMClient,
    load_config_from_env,
)

from .mock import (
    MockLLMClient,
    get_mock_candidate,
    list_mock_candidates,
)

from .replay import (
    ReplayLLMClient,
    save_response_as_fixture,
)

from .prompts import (
    build_generation_prompt,
    build_feedback_prompt,
    build_refinement_prompt,
)

from .parser import (
    parse_llm_response,
    extract_code_blocks,
    extract_function_name,
)


def create_client(config: LLMConfig):
    """
    Create an LLM client based on configuration.
    
    Auto-selects the appropriate client type:
    - MOCK -> MockLLMClient
    - REPLAY -> ReplayLLMClient
    - Others -> LLMClient (HTTP)
    
    Args:
        config: LLM configuration
        
    Returns:
        Client instance (LLMClient, MockLLMClient, or ReplayLLMClient)
        
    Example:
        >>> config = LLMConfig(provider=LLMProvider.MOCK, base_url="mock://", model="mock")
        >>> with create_client(config) as client:
        ...     response = client.generate(request)
    """
    if config.provider == LLMProvider.MOCK:
        return MockLLMClient(config)
    elif config.provider == LLMProvider.REPLAY:
        return ReplayLLMClient(config)
    else:
        return LLMClient(config)


__all__ = [
    # Models
    "LLMProvider",
    "LLMConfig",
    "GenerationRequest",
    "LLMResponse",
    "ParseResult",
    
    # Clients
    "LLMClient",
    "MockLLMClient",
    "ReplayLLMClient",
    "create_client",
    
    # Configuration
    "load_config_from_env",
    
    # Prompts
    "build_generation_prompt",
    "build_feedback_prompt",
    "build_refinement_prompt",
    
    # Parsing
    "parse_llm_response",
    "extract_code_blocks",
    "extract_function_name",
    
    # Mock utilities
    "get_mock_candidate",
    "list_mock_candidates",
    
    # Replay utilities
    "save_response_as_fixture",
]
