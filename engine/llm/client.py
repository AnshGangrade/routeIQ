"""
Runtime LLM client for heuristic generation.

This module provides the HTTP client for interacting with OpenAI-compatible
LLM APIs. It is completely separate from Kiro's development model.
"""

import httpx
import time
from typing import Dict, Any, Optional

from .models import LLMConfig, GenerationRequest, LLMResponse, LLMProvider


class LLMClient:
    """
    HTTP client for OpenAI-compatible LLM APIs.
    
    Supports multiple providers (OpenAI, Groq, local models, etc.) via
    configurable base URL and headers.
    
    Safety:
    - Never logs API keys
    - No automatic retries (cost control)
    - Clear error messages without leaking secrets
    
    Example:
        >>> from engine.llm import LLMConfig, LLMClient, GenerationRequest
        >>> config = LLMConfig(
        ...     provider=LLMProvider.OPENAI,
        ...     api_key="sk-...",
        ...     base_url="https://api.openai.com/v1",
        ...     model="gpt-4",
        ...     temperature=0.7
        ... )
        >>> client = LLMClient(config)
        >>> request = GenerationRequest(prompt="Generate a routing heuristic...")
        >>> response = client.generate(request)
    """
    
    def __init__(self, config: LLMConfig):
        """
        Initialize the LLM client.
        
        Args:
            config: LLM configuration
            
        Raises:
            ValueError: If config is invalid for the provider
        """
        self.config = config
        
        # Validate configuration
        if config.provider not in [LLMProvider.MOCK, LLMProvider.REPLAY]:
            if not config.api_key:
                raise ValueError(f"API key required for provider '{config.provider.value}'")
        
        # Create HTTP client
        self.client = httpx.Client(timeout=config.timeout)
    
    def __enter__(self):
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
    
    def close(self):
        """Close the HTTP client."""
        self.client.close()
    
    def generate(self, request: GenerationRequest) -> LLMResponse:
        """
        Generate a heuristic candidate from the LLM.
        
        Makes a POST request to the /chat/completions endpoint following
        the OpenAI API format.
        
        Args:
            request: Generation request with prompt and metadata
            
        Returns:
            LLM response with generated content
            
        Raises:
            RuntimeError: If the API request fails
            ValueError: If the response format is invalid
        """
        start_time = time.time()
        
        # Build request payload (OpenAI chat completions format)
        payload = {
            "model": self.config.model,
            "messages": [
                {
                    "role": "user",
                    "content": request.prompt
                }
            ],
            "temperature": self.config.temperature,
        }
        
        # Build headers
        headers = {
            "Content-Type": "application/json",
        }
        
        # Add authorization header (never log this!)
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"
        
        # Make request
        try:
            # Construct endpoint, handling trailing slashes correctly
            base = self.config.base_url.rstrip('/')
            endpoint = f"{base}/chat/completions"
            
            response = self.client.post(
                endpoint,
                json=payload,
                headers=headers
            )
            
            response.raise_for_status()
            
        except httpx.HTTPStatusError as e:
            # Handle HTTP errors without leaking API key
            status = e.response.status_code
            
            message = "Invalid API key" if status == 401 else "Provider rejected the request"
            raise RuntimeError(f"LLM API request failed ({status}): {message}") from None
        except httpx.RequestError as e:
            raise RuntimeError(f"LLM API request failed: {type(e).__name__}") from None

        # Parse response
        try:
            data = response.json()
        except Exception as e:
            raise ValueError("Failed to parse LLM response as JSON") from e
        
        # Extract content from OpenAI format
        try:
            choices = data.get("choices", [])
            if not choices:
                raise ValueError("No choices in LLM response")
            
            message = choices[0].get("message", {})
            content = message.get("content", "")
            
            if not content:
                raise ValueError("Empty content in LLM response")
            
        except (KeyError, IndexError, TypeError) as e:
            raise ValueError(f"Invalid LLM response format: {e}") from e
        
        # Build response metadata
        elapsed = time.time() - start_time
        metadata = {
            "latency_seconds": elapsed,
            "generation_id": request.generation_id,
        }
        
        # Add token usage if available
        if "usage" in data:
            metadata["usage"] = data["usage"]
        
        # Add request metadata
        metadata.update(request.metadata)
        
        return LLMResponse(
            raw_content=content,
            provider=self.config.provider.value,
            model=self.config.model,
            generation_id=request.generation_id,
            metadata=metadata
        )
    
    def __repr__(self) -> str:
        return f"LLMClient(config={self.config})"


def load_config_from_env(*, model_override: Optional[str] = None, temperature_override: Optional[float] = None) -> LLMConfig:
    """
    Load LLM configuration from environment variables.
    
    Expected variables:
    - LLM_PROVIDER: Provider name (default: "openai")
    - LLM_API_KEY: API key (required unless using mock/replay)
    - LLM_BASE_URL: API base URL (required)
    - LLM_MODEL: Model identifier (required)
    - LLM_TEMPERATURE: Sampling temperature (default: 0.7)
    - LLM_TIMEOUT: Request timeout in seconds (default: 30.0)
    
    Returns:
        LLM configuration
        
    Raises:
        ValueError: If required variables are missing
    
    Example:
        >>> import os
        >>> os.environ["LLM_PROVIDER"] = "openai"
        >>> os.environ["LLM_API_KEY"] = "sk-..."
        >>> os.environ["LLM_BASE_URL"] = "https://api.openai.com/v1"
        >>> os.environ["LLM_MODEL"] = "gpt-4"
        >>> config = load_config_from_env()
    """
    import os
    
    # Read only the process environment; never load secret files implicitly.
    
    # Read configuration
    provider = os.getenv("LLM_PROVIDER", "openai")
    api_key = os.getenv("LLM_API_KEY")
    base_url = os.getenv("LLM_BASE_URL")
    model = model_override if model_override is not None else os.getenv("LLM_MODEL")
    temperature = temperature_override if temperature_override is not None else float(os.getenv("LLM_TEMPERATURE", "0.7"))
    timeout = float(os.getenv("LLM_TIMEOUT", "30.0"))
    
    # Validate required fields
    if not base_url:
        raise ValueError("LLM_BASE_URL environment variable is required")
    
    if not model:
        raise ValueError("LLM_MODEL environment variable is required")
    
    # API key not required for mock/replay modes
    provider_enum = LLMProvider(provider.lower())
    if provider_enum not in [LLMProvider.MOCK, LLMProvider.REPLAY]:
        if not api_key:
            raise ValueError(f"LLM_API_KEY required for provider '{provider}'")
    
    return LLMConfig(
        provider=provider_enum,
        api_key=api_key,
        base_url=base_url,
        model=model,
        temperature=temperature,
        timeout=timeout
    )
