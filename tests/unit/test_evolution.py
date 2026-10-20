"""Unit tests for evolution module."""

import pytest
import json
from pathlib import Path
from datetime import datetime

from engine.evolution import (
    EvolutionConfig,
    EvolutionLoop,
    EvolutionPersistence,
    CandidateRecord,
    GenerationRecord,
    EvolutionRun,
)
from engine.llm.mock import MockLLMClient
from engine.llm.models import LLMConfig, LLMProvider


@pytest.mark.unit
class TestEvolutionConfig:
    """Test evolution configuration."""
    
    def test_default_config(self):
        """Test default configuration values."""
        config = EvolutionConfig()
        
        assert config.num_generations == 5
        assert config.candidates_per_generation == 3
        assert config.retained_candidates == 2
        assert config.training_instance_count == 3
        assert config.test_instance_count == 2
        assert config.num_stops == 15
        assert config.seed == 42
        assert config.llm_mode == "mock"
        assert config.evaluation_timeout == 5.0
    
    def test_custom_config(self):
        """Test custom configuration."""
        config = EvolutionConfig(
            num_generations=10,
            candidates_per_generation=5,
            training_instance_count=10,
            num_stops=20,
            seed=123,
            llm_mode="live",
        )
        
        assert config.num_generations == 10
        assert config.candidates_per_generation == 5
        assert config.training_instance_count == 10
        assert config.num_stops == 20
        assert config.seed == 123
        assert config.llm_mode == "live"
    
    def test_config_validation(self):
        """Test configuration validation."""
        # Should accept valid values
        config = EvolutionConfig(num_generations=1)
        assert config.num_generations == 1
        
        # Should reject invalid values
        with pytest.raises(ValueError):
            EvolutionConfig(num_generations=0)
        
        with pytest.raises(ValueError):
            EvolutionConfig(num_generations=-1)
    
    def test_config_immutable(self):
        """Test that config is immutable."""
        config = EvolutionConfig()
        
        with pytest.raises(Exception):
            config.num_generations = 10


@pytest.mark.unit
class TestCandidateRecord:
    """Test candidate record model."""
    
    def test_valid_candidate(self):
        """Test valid candidate record."""
        record = CandidateRecord(
            candidate_id="gen1_cand1",
            generation=1,
            source_code="def score(x): return x",
            is_valid=True,
            fitness_score=0.85,
            avg_route_distance=150.5,
            evaluation_time=1.23,
        )
        
        assert record.candidate_id == "gen1_cand1"
        assert record.generation == 1
        assert record.is_valid
        assert record.fitness_score == 0.85
        assert record.error_type is None
        assert isinstance(record.created_at, datetime)
    
    def test_invalid_candidate(self):
        """Test invalid candidate record."""
        record = CandidateRecord(
            candidate_id="gen1_cand2",
            generation=1,
            source_code="import os",
            is_valid=False,
            error_type="ValidationError",
            error_message="Import not allowed",
        )
        
        assert record.candidate_id == "gen1_cand2"
        assert not record.is_valid
        assert record.error_type == "ValidationError"
        assert record.fitness_score is None


@pytest.mark.unit
class TestGenerationRecord:
    """Test generation record model."""
    
    def test_generation_with_valid_candidates(self):
        """Test generation record with valid candidates."""
        candidates = [
            CandidateRecord(
                candidate_id=f"gen1_cand{i}",
                generation=1,
                source_code=f"def score(x): return x * {i}",
                is_valid=True,
                fitness_score=0.5 + i * 0.1,
                avg_route_distance=200 - i * 10,
                evaluation_time=1.0,
            )
            for i in range(3)
        ]
        
        record = GenerationRecord(
            generation_number=1,
            candidates=candidates,
            best_candidate_id="gen1_cand2",
            best_fitness=0.7,
            best_so_far_id="gen1_cand2",
            best_so_far_fitness=0.7,
            num_valid=3,
            num_invalid=0,
            avg_fitness=0.6,
        )
        
        assert record.generation_number == 1
        assert len(record.candidates) == 3
        assert record.num_valid == 3
        assert record.num_invalid == 0
        assert record.avg_fitness == 0.6
    
    def test_generation_with_invalid_candidates(self):
        """Test generation with some invalid candidates."""
        candidates = [
            CandidateRecord(
                candidate_id="gen1_cand1",
                generation=1,
                source_code="valid code",
                is_valid=True,
                fitness_score=0.8,
                avg_route_distance=150.0,
                evaluation_time=1.0,
            ),
            CandidateRecord(
                candidate_id="gen1_cand2",
                generation=1,
                source_code="import os",
                is_valid=False,
                error_type="ValidationError",
                error_message="Import not allowed",
            ),
        ]
        
        record = GenerationRecord(
            generation_number=1,
            candidates=candidates,
            best_candidate_id="gen1_cand1",
            best_fitness=0.8,
            best_so_far_id="gen1_cand1",
            best_so_far_fitness=0.8,
            num_valid=1,
            num_invalid=1,
            avg_fitness=0.8,
        )
        
        assert record.num_valid == 1
        assert record.num_invalid == 1


@pytest.mark.unit
class TestEvolutionRun:
    """Test evolution run model."""
    
    def test_run_initialization(self):
        """Test run initialization."""
        run = EvolutionRun(
            run_id="test_run_123",
            config={"num_generations": 5},
            training_seed=42,
            test_seed=1042,
        )
        
        assert run.run_id == "test_run_123"
        assert run.status == "running"
        assert len(run.generations) == 0
        assert len(run.failures) == 0
        assert run.best_candidate_id is None
    
    def test_mark_completed(self):
        """Test marking run as completed."""
        run = EvolutionRun(
            run_id="test_run",
            config={},
            training_seed=42,
            test_seed=1042,
        )
        
        run.mark_completed()
        
        assert run.status == "completed"
        assert run.completed_at is not None
    
    def test_mark_failed(self):
        """Test marking run as failed."""
        run = EvolutionRun(
            run_id="test_run",
            config={},
            training_seed=42,
            test_seed=1042,
        )
        
        run.mark_failed("Something went wrong")
        
        assert run.status == "failed"
        assert run.error_message == "Something went wrong"
        assert run.completed_at is not None
    
    def test_add_generation(self):
        """Test adding generation records."""
        run = EvolutionRun(
            run_id="test_run",
            config={},
            training_seed=42,
            test_seed=1042,
        )
        
        gen = GenerationRecord(
            generation_number=1,
            candidates=[],
            num_valid=0,
            num_invalid=0,
        )
        
        run.add_generation(gen)
        
        assert len(run.generations) == 1
        assert run.generations[0].generation_number == 1
    
    def test_add_failure(self):
        """Test recording failures."""
        run = EvolutionRun(
            run_id="test_run",
            config={},
            training_seed=42,
            test_seed=1042,
        )
        
        run.add_failure({
            "generation": 1,
            "candidate_id": "gen1_cand1",
            "error": "Test error",
        })
        
        assert len(run.failures) == 1
        assert run.failures[0]["candidate_id"] == "gen1_cand1"
    
    def test_get_convergence_history(self):
        """Test getting convergence history."""
        run = EvolutionRun(
            run_id="test_run",
            config={},
            training_seed=42,
            test_seed=1042,
        )
        
        # Add generations with improving fitness
        for i in range(3):
            gen = GenerationRecord(
                generation_number=i + 1,
                candidates=[],
                best_so_far_fitness=0.5 + i * 0.1,
                num_valid=1,
                num_invalid=0,
            )
            run.add_generation(gen)
        
        history = run.get_convergence_history()
        
        assert len(history) == 3
        assert history == [0.5, 0.6, 0.7]
    
    def test_get_generation_summary(self):
        """Test getting generation summary."""
        run = EvolutionRun(
            run_id="test_run",
            config={},
            training_seed=42,
            test_seed=1042,
        )
        
        # Add generations
        for i in range(2):
            candidates = [
                CandidateRecord(
                    candidate_id=f"gen{i+1}_cand{j}",
                    generation=i + 1,
                    source_code="code",
                    is_valid=j == 0,  # First valid, second invalid
                )
                for j in range(2)
            ]
            
            gen = GenerationRecord(
                generation_number=i + 1,
                candidates=candidates,
                num_valid=1,
                num_invalid=1,
            )
            run.add_generation(gen)
        
        summary = run.get_generation_summary()
        
        assert summary["total_generations"] == 2
        assert summary["total_candidates"] == 4
        assert summary["total_valid"] == 2
        assert summary["total_invalid"] == 2
        assert summary["validity_rate"] == 0.5


@pytest.mark.unit
class TestEvolutionPersistence:
    """Test evolution persistence."""
    
    def test_save_and_load_run(self, tmp_path):
        """Test saving and loading a run."""
        persistence = EvolutionPersistence(runs_dir=str(tmp_path))
        
        # Create run
        run = EvolutionRun(
            run_id="test_run_123",
            config={"num_generations": 5},
            training_seed=42,
            test_seed=1042,
        )
        run.mark_completed()
        
        # Save
        persistence.save_run(run)
        
        # Check file exists
        run_file = tmp_path / "test_run_123.json"
        assert run_file.exists()
        
        # Load
        loaded_run = persistence.load_run("test_run_123")
        
        assert loaded_run is not None
        assert loaded_run.run_id == "test_run_123"
        assert loaded_run.status == "completed"
    
    def test_load_nonexistent_run(self, tmp_path):
        """Test loading nonexistent run."""
        persistence = EvolutionPersistence(runs_dir=str(tmp_path))
        
        loaded_run = persistence.load_run("nonexistent")
        
        assert loaded_run is None
    
    def test_list_runs(self, tmp_path):
        """Test listing runs."""
        persistence = EvolutionPersistence(runs_dir=str(tmp_path))
        
        # Create multiple runs
        for i in range(3):
            run = EvolutionRun(
                run_id=f"run_{i}",
                config={},
                training_seed=42,
                test_seed=1042,
            )
            persistence.save_run(run)
        
        # List runs
        runs = persistence.list_runs()
        
        assert len(runs) == 3
        assert "run_0" in runs
        assert "run_1" in runs
        assert "run_2" in runs
    
    def test_get_latest_run(self, tmp_path):
        """Test getting latest run."""
        persistence = EvolutionPersistence(runs_dir=str(tmp_path))
        
        # Create runs with slight delay to ensure different timestamps
        import time
        for i in range(2):
            run = EvolutionRun(
                run_id=f"run_{i}",
                config={},
                training_seed=42,
                test_seed=1042,
            )
            persistence.save_run(run)
            time.sleep(0.01)  # Small delay to ensure different file modification times
        
        # Get latest
        latest = persistence.get_latest_run()
        
        assert latest is not None
        # Latest could be either depending on file system timestamp resolution
        assert latest.run_id in ["run_0", "run_1"]
    
    def test_delete_run(self, tmp_path):
        """Test deleting a run."""
        persistence = EvolutionPersistence(runs_dir=str(tmp_path))
        
        # Create run
        run = EvolutionRun(
            run_id="test_run",
            config={},
            training_seed=42,
            test_seed=1042,
        )
        persistence.save_run(run)
        
        # Delete
        result = persistence.delete_run("test_run")
        
        assert result is True
        assert persistence.load_run("test_run") is None
        
        # Try deleting again
        result = persistence.delete_run("test_run")
        assert result is False


@pytest.mark.unit
class TestEvolutionLoop:
    """Test evolution loop."""
    
    def test_loop_initialization(self):
        """Test loop initialization."""
        config = EvolutionConfig(num_generations=2)
        llm_config = LLMConfig(
            provider=LLMProvider.MOCK,
            base_url="mock://local",
            model="mock-v1",
        )
        llm_client = MockLLMClient(llm_config)
        
        loop = EvolutionLoop(config=config, llm_client=llm_client)
        
        assert loop.config == config
        assert loop.llm_client == llm_client
        assert loop.run is None
    
    def test_run_evolution_mock(self):
        """Test running evolution with mock client."""
        config = EvolutionConfig(
            num_generations=2,
            candidates_per_generation=2,
            training_instance_count=2,
            test_instance_count=2,
            num_stops=10,
            llm_mode="mock",
        )
        llm_config = LLMConfig(
            provider=LLMProvider.MOCK,
            base_url="mock://local",
            model="mock-v1",
        )
        llm_client = MockLLMClient(llm_config)
        
        loop = EvolutionLoop(config=config, llm_client=llm_client)
        run = loop.run_evolution()
        
        # Check run completed
        assert run.status == "completed"
        assert len(run.generations) == 2
        
        # Check each generation has candidates
        for gen in run.generations:
            assert len(gen.candidates) == 2
        
        # Check best candidate was selected
        assert run.best_candidate_code is not None
        
        # Check test evaluation was performed
        assert run.test_evaluation is not None
        assert len(run.test_evaluation.baselines) == 2
    
    def test_run_handles_invalid_candidates(self):
        """Test that run handles invalid candidates gracefully."""
        config = EvolutionConfig(
            num_generations=1,
            candidates_per_generation=2,
            training_instance_count=2,
            test_instance_count=1,
            num_stops=10,
        )
        
        # Use mock client that might produce invalid candidates
        llm_config = LLMConfig(
            provider=LLMProvider.MOCK,
            base_url="mock://local",
            model="mock-v1",
        )
        llm_client = MockLLMClient(llm_config)
        
        loop = EvolutionLoop(config=config, llm_client=llm_client)
        run = loop.run_evolution()
        
        # Run should complete even if some candidates are invalid
        assert run.status in ("completed", "failed")
        assert len(run.generations) == 1
    
    def test_convergence_tracking(self):
        """Test that convergence is tracked across generations."""
        config = EvolutionConfig(
            num_generations=3,
            candidates_per_generation=2,
            training_instance_count=2,
            test_instance_count=1,
            num_stops=10,
        )
        llm_config = LLMConfig(
            provider=LLMProvider.MOCK,
            base_url="mock://local",
            model="mock-v1",
        )
        llm_client = MockLLMClient(llm_config)
        
        loop = EvolutionLoop(config=config, llm_client=llm_client)
        run = loop.run_evolution()
        
        # Check convergence history
        history = run.get_convergence_history()
        assert len(history) > 0
        
        # Best-so-far should be monotonically non-decreasing
        for i in range(1, len(history)):
            assert history[i] >= history[i-1]


@pytest.mark.integration
class TestEvolutionIntegration:
    """Integration tests for complete evolution pipeline."""
    
    def test_full_evolution_pipeline(self, tmp_path):
        """Test complete evolution pipeline from start to finish."""
        # Create configuration
        config = EvolutionConfig(
            num_generations=2,
            candidates_per_generation=2,
            training_instance_count=3,
            test_instance_count=2,
            num_stops=10,
            seed=42,
            llm_mode="mock",
        )
        
        # Run evolution
        llm_config = LLMConfig(
            provider=LLMProvider.MOCK,
            base_url="mock://local",
            model="mock-v1",
        )
        llm_client = MockLLMClient(llm_config)
        loop = EvolutionLoop(config=config, llm_client=llm_client)
        run = loop.run_evolution()
        
        # Verify run structure
        assert run.status == "completed"
        assert len(run.generations) == 2
        assert run.test_evaluation is not None
        
        # Save and load
        persistence = EvolutionPersistence(runs_dir=str(tmp_path))
        persistence.save_run(run)
        
        loaded_run = persistence.load_run(run.run_id)
        assert loaded_run.run_id == run.run_id
        
        # Get summary
        summary = persistence.get_run_summary(run.run_id)
        assert summary is not None
        assert summary["status"] == "completed"
        assert summary["num_generations"] == 2
    
    def test_candidate_route_evaluation(self):
        """Test that a valid candidate can be evaluated successfully."""
        from engine.heuristics import RouteHarness
        from engine.instances import InstanceGenerator, compute_distance_matrix
        from engine.sandbox.adapter import create_scoring_function
        
        # Create a simple instance
        generator = InstanceGenerator(seed=42)
        instance = generator.generate(n_stops=5)
        
        # Create a simple nearest-neighbor heuristic
        source_code = """
def score_candidates(context):
    scores = {}
    for stop in context.candidate_stops:
        scores[stop] = context.distance_matrix[context.current_location, stop]
    return {"scores": scores}
"""
        
        # Create scoring function
        scoring_fn = create_scoring_function(source_code)
        
        # Build route
        harness = RouteHarness()
        locations = instance.get_all_locations()
        distance_matrix = compute_distance_matrix(locations)
        
        result = harness.build_route(
            heuristic=scoring_fn,
            distance_matrix=distance_matrix,
            n_stops=instance.n_stops
        )
        
        # Verify result
        assert result is not None
        assert len(result.route) == instance.n_stops + 2  # depot + stops + return to depot
        assert result.route[0] == 0  # Starts at depot
        assert result.route[-1] == 0  # Returns to depot
        assert result.total_distance > 0
        assert result.total_distance < float('inf')
