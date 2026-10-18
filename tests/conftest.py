"""
Pytest configuration and shared fixtures.
"""

import pytest
import numpy as np
from pathlib import Path


@pytest.fixture
def project_root():
    """Return the project root directory."""
    return Path(__file__).parent.parent


@pytest.fixture
def test_data_dir(project_root):
    """Return the test data directory."""
    data_dir = project_root / "tests" / "data"
    data_dir.mkdir(exist_ok=True)
    return data_dir


@pytest.fixture
def sample_seed():
    """Return a fixed seed for reproducible tests."""
    return 42


@pytest.fixture
def sample_random_state(sample_seed):
    """Return a seeded random state."""
    return np.random.RandomState(sample_seed)


@pytest.fixture
def temp_runs_dir(tmp_path):
    """Create a temporary runs directory for test outputs."""
    runs_dir = tmp_path / "runs"
    runs_dir.mkdir()
    return runs_dir
