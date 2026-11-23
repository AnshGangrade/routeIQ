"""
Data models for LLM client and heuristic generation.
"""

from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field
from enum import Enum


class LLMProvider(str, Enum):
    """Supported LLM providers."""
    OPENAI = "openai"
    GROQ = "groq"
    LOCAL = "local"
    ANTHROPIC = "anthropic"
    MOCK = "mock"
    REPLAY = "replay"


class LLMConfig(BaseModel):
    """
    Configuration for the runtime LLM client.
    
    Read from environment variables:
    - LLM_PROVIDER: Provider name (openai, groq, local, etc.)
    - LLM_API_KEY: API key (required for most providers)
    - LLM_BASE_URL: Base URL for API endpoint
    - LLM_MODEL: Model identifier
    - LLM_TEMPERATURE: Sampling temperature (0.0-1.0)
    
    For testing:
    - Set provider="mock" for predefined candidates
    - Set provider="replay" to load from fixtures
    
    Example:
        >>> config = LLMConfig(
        ...     provider=LLMProvider.OPENAI,
        ...     api_key="sk-...",
        ...     base_url="https://api.openai.com/v1",
        ...     model="gpt-4",
        ...     temperature=0.7
        ... )
    """
    provider: LLMProvider = Field(..., description="LLM provider")
    api_key: Optional[str] = Field(None, repr=False, description="API key (not required for mock/replay)")
    base_url: str = Field(..., description="API base URL")
    model: str = Field(..., description="Model identifier")
    temperature: float = Field(default=0.7, ge=0.0, le=1.0, description="Sampling temperature")
    timeout: float = Field(default=30.0, ge=1.0, description="Request timeout in seconds")
    replay_fixtures: List[str] = Field(default_factory=list, description="Explicit cyclic fixture sequence for offline evolution")
    
    def __repr__(self) -> str:
        # Never log API keys
        key_preview = "***" if self.api_key else None
        return (
            f"LLMConfig(provider={self.provider.value}, "
            f"model={self.model}, key={'set' if self.api_key else 'unset'})"
        )


class GenerationRequest(BaseModel):
    """
    Request for heuristic generation.
    
    Attributes:
        prompt: System/user prompt for the LLM
        generation_id: Optional identifier for this generation
        metadata: Optional metadata (iteration number, parent fitness, etc.)
    """
    prompt: str = Field(..., description="Prompt for the LLM")
    generation_id: Optional[str] = Field(None, description="Generation identifier")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Request metadata")
    
    def __repr__(self) -> str:
        prompt_preview = self.prompt[:50] + "..." if len(self.prompt) > 50 else self.prompt
        return f"GenerationRequest(id={self.generation_id}, prompt='{prompt_preview}')"


class LLMResponse(BaseModel):
    """
    Response from LLM API.
    
    Attributes:
        raw_content: Full text response from the LLM
        provider: Provider that generated this response
        model: Model used for generation
        generation_id: Request identifier (if provided)
        metadata: Additional response metadata (tokens, latency, etc.)
    """
    raw_content: str = Field(..., description="Raw LLM response text")
    provider: str = Field(..., description="Provider name")
    model: str = Field(..., description="Model identifier")
    generation_id: Optional[str] = Field(None, description="Generation identifier")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Response metadata")
    
    def __repr__(self) -> str:
        preview = self.raw_content[:50] + "..." if len(self.raw_content) > 50 else self.raw_content
        return f"LLMResponse(provider={self.provider}, model={self.model}, content='{preview}')"


class ParseResult(BaseModel):
    """
    Result of parsing an LLM response into candidate heuristic.
    
    Attributes:
        success: Whether parsing succeeded
        source_code: Extracted Python source code (if successful)
        function_name: Detected function name (if successful)
        errors: List of parsing error messages
        warnings: List of non-blocking warnings
    """
    success: bool = Field(..., description="Whether parsing succeeded")
    source_code: Optional[str] = Field(None, description="Extracted source code")
    function_name: Optional[str] = Field(None, description="Detected function name")
    errors: List[str] = Field(default_factory=list, description="Parsing errors")
    warnings: List[str] = Field(default_factory=list, description="Parsing warnings")
    
    def __repr__(self) -> str:
        if self.success:
            return f"ParseResult(SUCCESS, function={self.function_name})"
        return f"ParseResult(FAILED, errors={len(self.errors)})"
