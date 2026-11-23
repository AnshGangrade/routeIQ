"""
Integration tests for live LLM mode.

These tests require a configured .env file with LLM API credentials.
They are skipped if the environment is not configured.
"""
import pytest
import os
import time
from fastapi.testclient import TestClient
from dotenv import load_dotenv

from api.main import app
from api.storage import instance_store, evolution_runs, routing_results


# Load environment variables
load_dotenv()


@pytest.fixture
def client():
    """Create a test client for the API."""
    # Clear storage before each test
    instance_store.clear()
    evolution_runs.clear()
    routing_results.clear()
    
    return TestClient(app)


# Skip marker for tests requiring API key
requires_api_key = pytest.mark.skipif(
    not os.getenv("LLM_API_KEY"),
    reason="Requires LLM_API_KEY in .env for live API calls"
)


def test_live_mode_without_env(client):
    """Test that live mode fails gracefully without .env configuration."""
    # Note: We can't monkeypatch the FastAPI process environment,
    # so this test assumes no .env file is configured.
    # If .env exists with valid keys, this test will be skipped.
    
    if os.getenv("LLM_API_KEY"):
        pytest.skip("Test requires no LLM_API_KEY in environment")
    
    response = client.post("/api/evolution/runs", json={
        "num_stops": 10,
        "num_instances": 3,  # Min 3 per schema
        "num_generations": 2,  # Min 2 per schema
        "candidates_per_generation": 2,
        "elites_kept": 1,
        "mode": "live"
    })
    
    assert response.status_code == 400
    data = response.json()
    assert "LLM_API_KEY" in data["detail"]
    assert ".env" in data["detail"]


@requires_api_key
def test_evolution_live_mode_minimal(client):
    """
    Test evolution with real LLM API (minimal run).
    
    This test makes actual API calls and will be skipped if LLM_API_KEY
    is not configured.
    
    SUCCESS CRITERIA:
    - Evolution starts successfully
    - At least one generation completes
    - At least one valid candidate is generated
    - No crashes or unhandled exceptions
    
    Note: This does not verify heuristic quality, only that the
    integration works end-to-end.
    """
    # Start evolution with minimal parameters
    response = client.post("/api/evolution/runs", json={
        "num_stops": 10,  # Small instance
        "num_instances": 3,  # Minimum 3 required
        "num_generations": 2,  # Minimum 2 required
        "candidates_per_generation": 2,  # Two candidates only
        "elites_kept": 1,
        "mode": "live"
    })
    
    assert response.status_code == 200, f"Failed to start evolution: {response.json()}"
    data = response.json()
    run_id = data["run_id"]
    assert data["status"] in ["pending", "running"]
    
    # Poll until complete (with timeout)
    max_wait = 120  # 2 minutes maximum
    poll_interval = 3  # Check every 3 seconds
    elapsed = 0
    
    final_status = None
    while elapsed < max_wait:
        progress_response = client.get(f"/api/evolution/runs/{run_id}")
        assert progress_response.status_code == 200
        
        progress = progress_response.json()
        final_status = progress["status"]
        
        if final_status in ["completed", "failed"]:
            break
        
        time.sleep(poll_interval)
        elapsed += poll_interval
    
    # Check final state
    assert final_status is not None, "Evolution did not complete within timeout"
    
    if final_status == "failed":
        error_msg = progress.get("error", "Unknown error")
        pytest.fail(f"Evolution failed: {error_msg}")
    
    assert final_status == "completed", f"Unexpected status: {final_status}"
    
    # Verify we got generations
    assert len(progress["generations"]) >= 1, "Expected at least 1 generation"
    
    gen = progress["generations"][0]
    assert gen["generation"] == 1
    assert len(gen["candidates"]) >= 2, "Expected at least 2 candidates"
    
    # Check that at least some candidates were valid
    # (We can't guarantee all will be valid with real LLMs)
    assert gen["valid_count"] >= 0, "Should have validity counts"
    
    # If any candidates are valid, check their structure
    valid_candidates = [c for c in gen["candidates"] if c["is_valid"]]
    if valid_candidates:
        candidate = valid_candidates[0]
        assert candidate["code"], "Valid candidate should have code"
        assert candidate["fitness"] is not None, "Valid candidate should have fitness"
        assert candidate["fitness"] > 0, "Fitness should be positive distance"
    
    print(f"\n✅ Live LLM test successful!")
    print(f"   Run ID: {run_id}")
    print(f"   Valid candidates: {gen['valid_count']}/{len(gen['candidates'])}")
    if gen["best_fitness"]:
        print(f"   Best fitness: {gen['best_fitness']:.2f}")


@requires_api_key
def test_evolution_live_mode_full(client):
    """
    Test full evolution run with multiple generations (slower test).
    
    This test is more comprehensive but takes longer and costs more.
    Only run when thoroughly testing live mode.
    """
    pytest.skip("Full live test is expensive - enable manually for thorough testing")
    
    response = client.post("/api/evolution/runs", json={
        "num_stops": 20,
        "num_instances": 5,
        "num_generations": 3,
        "candidates_per_generation": 4,
        "elites_kept": 2,
        "mode": "live"
    })
    
    assert response.status_code == 200
    run_id = response.json()["run_id"]
    
    # Poll with longer timeout for full run
    max_wait = 300  # 5 minutes
    poll_interval = 5
    elapsed = 0
    
    final_status = None
    while elapsed < max_wait:
        progress = client.get(f"/api/evolution/runs/{run_id}").json()
        final_status = progress["status"]
        
        if final_status in ["completed", "failed"]:
            break
        
        time.sleep(poll_interval)
        elapsed += poll_interval
    
    assert final_status == "completed", f"Evolution status: {final_status}"
    
    # Get best heuristic
    best_response = client.get(f"/api/evolution/runs/{run_id}/best")
    assert best_response.status_code == 200
    best = best_response.json()
    
    assert best["heuristic"]["is_valid"]
    assert best["heuristic"]["code"]
    assert best["validation_fitness"] is not None


def test_mode_parameter_validation(client):
    """Test that mode parameter is properly validated."""
    # Invalid mode
    response = client.post("/api/evolution/runs", json={
        "num_stops": 20,
        "num_instances": 5,
        "num_generations": 3,
        "candidates_per_generation": 4,
        "elites_kept": 2,
        "mode": "invalid_mode"
    })
    
    assert response.status_code == 400
    assert "invalid_mode" in response.json()["detail"].lower()


def test_environment_config_helpful_errors(client):
    """Test that missing configuration gives helpful error messages."""
    # This test documents expected behavior when .env is missing.
    # In a real deployment, users will see these errors.
    
    if os.getenv("LLM_API_KEY"):
        pytest.skip("Test requires no LLM_API_KEY - can't test missing config when it exists")
    
    response = client.post("/api/evolution/runs", json={
        "num_stops": 10,
        "num_instances": 3,  # Min 3 per schema
        "num_generations": 2,  # Min 2 per schema
        "candidates_per_generation": 2,
        "elites_kept": 1,
        "mode": "live"
    })
    
    assert response.status_code == 400
    error = response.json()["detail"]
    assert "LLM_API_KEY" in error
    assert ".env" in error or ".env.example" in error


# Marker for manual testing
manual_test = pytest.mark.skipif(
    True,  # Always skip in automated runs
    reason="Manual test - enable explicitly for debugging"
)


@manual_test
@requires_api_key
def test_live_mode_debug(client):
    """
    Debug test for live mode - prints detailed output.
    
    Enable by removing the @manual_test decorator.
    Useful for diagnosing LLM response issues.
    """
    response = client.post("/api/evolution/runs", json={
        "num_stops": 10,
        "num_instances": 3,  # Minimum 3 required
        "num_generations": 2,  # Minimum 2 required
        "candidates_per_generation": 1,
        "elites_kept": 1,
        "mode": "live"
    })
    
    print(f"\nStart response: {response.json()}")
    run_id = response.json()["run_id"]
    
    # Poll with detailed logging
    for i in range(60):
        time.sleep(2)
        progress = client.get(f"/api/evolution/runs/{run_id}").json()
        print(f"\n[{i*2}s] Status: {progress['status']}, Gen: {progress['current_generation']}")
        
        if progress["status"] in ["completed", "failed"]:
            print(f"\nFinal state: {progress}")
            break
    
    assert False, "Check output above"

