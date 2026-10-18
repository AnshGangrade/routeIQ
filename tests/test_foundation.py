"""
Foundation tests to verify project setup.
"""

import pytest
import sys
from pathlib import Path


def test_python_version():
    """Verify Python version meets minimum requirement."""
    assert sys.version_info >= (3, 10), "Python 3.10+ required"


def test_numpy_import():
    """Verify NumPy can be imported."""
    import numpy as np
    assert hasattr(np, '__version__')


def test_pydantic_import():
    """Verify Pydantic can be imported."""
    import pydantic
    assert hasattr(pydantic, '__version__')


def test_project_structure(project_root):
    """Verify essential project directories exist."""
    required_dirs = [
        "engine",
        "engine/instances",
        "engine/baselines",
        "engine/heuristics",
        "engine/llm",
        "engine/sandbox",
        "engine/evaluation",
        "engine/evolution",
        "engine/routing",
        "engine/metrics",
        "tests",
        "api",
    ]
    
    for dir_path in required_dirs:
        full_path = project_root / dir_path
        assert full_path.exists(), f"Missing required directory: {dir_path}"
        assert full_path.is_dir(), f"Not a directory: {dir_path}"


def test_gitignore_exists(project_root):
    """Verify .gitignore exists and contains critical patterns."""
    gitignore = project_root / ".gitignore"
    assert gitignore.exists(), ".gitignore not found"
    
    content = gitignore.read_text()
    critical_patterns = [".env", "venv/", "__pycache__", "runs/"]
    
    for pattern in critical_patterns:
        assert pattern in content, f"Missing .gitignore pattern: {pattern}"


def test_env_example_exists(project_root):
    """Verify .env.example exists and contains no secrets."""
    env_example = project_root / ".env.example"
    assert env_example.exists(), ".env.example not found"
    
    content = env_example.read_text()
    
    # Should contain variable names
    assert "LLM_API_KEY" in content
    assert "LLM_PROVIDER" in content
    
    # Should NOT contain actual secrets
    forbidden = ["sk-", "gsk_", "Bearer "]
    for secret_pattern in forbidden:
        assert secret_pattern not in content, "Found potential secret in .env.example"


@pytest.mark.unit
def test_sample_fixtures(sample_seed, sample_random_state):
    """Verify test fixtures work correctly."""
    assert sample_seed == 42
    assert sample_random_state.randint(0, 100) == 51  # Deterministic


@pytest.mark.unit
def test_temp_dirs(temp_runs_dir):
    """Verify temporary directory fixture works."""
    assert temp_runs_dir.exists()
    assert temp_runs_dir.is_dir()
    
    # Should be able to write to it
    test_file = temp_runs_dir / "test.txt"
    test_file.write_text("test")
    assert test_file.exists()
