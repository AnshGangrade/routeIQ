"""Configuration for evolutionary loop."""

from pydantic import BaseModel, Field, ConfigDict
from typing import Literal


class EvolutionConfig(BaseModel):
    """Configuration for evolution run.
    
    Conservative defaults suitable for laptop development and testing.
    """
    
    model_config = ConfigDict(frozen=True)
    
    # Evolution parameters
    num_generations: int = Field(
        default=5,
        ge=1,
        description="Number of evolution generations to run"
    )
    candidates_per_generation: int = Field(
        default=3,
        ge=1,
        description="How many candidates to generate per generation"
    )
    retained_candidates: int = Field(
        default=2,
        ge=1,
        description="How many top candidates to retain for next generation"
    )
    
    # Instance configuration
    training_instance_count: int = Field(
        default=3,
        ge=1,
        description="Number of training instances for candidate evaluation"
    )
    test_instance_count: int = Field(
        default=2,
        ge=1,
        description="Number of held-out test instances for final evaluation"
    )
    num_stops: int = Field(
        default=15,
        ge=2,
        description="Number of stops per instance"
    )
    num_drivers: int = Field(
        default=1,
        ge=1,
        description="Number of drivers (single driver for M7)"
    )
    seed: int = Field(
        default=42,
        description="Random seed for reproducibility"
    )
    
    # LLM configuration
    llm_mode: Literal["mock", "replay", "live"] = Field(
        default="mock",
        description="LLM client mode: mock (no API), replay (cached), or live"
    )
    
    # Evaluation limits
    evaluation_timeout: float = Field(
        default=5.0,
        gt=0,
        description="Timeout in seconds for candidate evaluation"
    )
    max_route_length: int = Field(
        default=1000,
        ge=1,
        description="Maximum allowed route length for safety"
    )
