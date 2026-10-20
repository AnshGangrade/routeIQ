"""Persistence for evolution runs."""

import json
from pathlib import Path
from typing import Optional, List
from datetime import datetime

from engine.evolution.models import EvolutionRun


class EvolutionPersistence:
    """Handles saving and loading evolution runs."""
    
    def __init__(self, runs_dir: str = "runs"):
        self.runs_dir = Path(runs_dir)
        self.runs_dir.mkdir(parents=True, exist_ok=True)
    
    def save_run(self, run: EvolutionRun):
        """Save evolution run to disk.
        
        Args:
            run: EvolutionRun to save
        """
        run_path = self.runs_dir / f"{run.run_id}.json"
        
        # Convert to JSON
        run_data = run.model_dump()
        
        # Handle datetime serialization
        run_json = json.dumps(run_data, indent=2, default=str)
        
        # Write to file
        run_path.write_text(run_json)
        
        print(f"Saved run to: {run_path}")
    
    def load_run(self, run_id: str) -> Optional[EvolutionRun]:
        """Load evolution run from disk.
        
        Args:
            run_id: Run ID to load
        
        Returns:
            EvolutionRun if found, None otherwise
        """
        run_path = self.runs_dir / f"{run_id}.json"
        
        if not run_path.exists():
            return None
        
        run_data = json.loads(run_path.read_text())
        return EvolutionRun(**run_data)
    
    def list_runs(self) -> List[str]:
        """List all saved run IDs.
        
        Returns:
            List of run IDs sorted by timestamp (newest first)
        """
        run_files = sorted(
            self.runs_dir.glob("run_*.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        return [p.stem for p in run_files]
    
    def get_latest_run(self) -> Optional[EvolutionRun]:
        """Get the most recently saved run.
        
        Returns:
            Latest EvolutionRun if any exist, None otherwise
        """
        runs = self.list_runs()
        if not runs:
            return None
        return self.load_run(runs[0])
    
    def delete_run(self, run_id: str) -> bool:
        """Delete a saved run.
        
        Args:
            run_id: Run ID to delete
        
        Returns:
            True if deleted, False if not found
        """
        run_path = self.runs_dir / f"{run_id}.json"
        
        if not run_path.exists():
            return False
        
        run_path.unlink()
        return True
    
    def get_run_summary(self, run_id: str) -> Optional[dict]:
        """Get summary of a run without loading full data.
        
        Args:
            run_id: Run ID to summarize
        
        Returns:
            Dictionary with summary info, None if not found
        """
        run = self.load_run(run_id)
        if not run:
            return None
        
        summary = {
            "run_id": run.run_id,
            "status": run.status,
            "started_at": run.started_at,
            "completed_at": run.completed_at,
            "num_generations": len(run.generations),
            "best_training_fitness": run.best_training_fitness,
        }
        
        # Add test results if available
        if run.test_evaluation:
            summary["test_evolved_distance"] = run.test_evaluation.evolved_avg_distance
            summary["test_improvement_vs_nn"] = run.test_evaluation.improvement_vs_nn_percent
            summary["test_improvement_vs_2opt"] = run.test_evaluation.improvement_vs_2opt_percent
        
        # Add generation stats
        gen_summary = run.get_generation_summary()
        summary.update(gen_summary)
        
        return summary
