"""
Candidate selection for evolutionary optimization.

Simple deterministic selection strategy based on fitness ranking.
"""

from typing import List, Dict, Optional
from .models import BenchmarkResult, SelectionResult
from .fitness import FitnessFunction, create_fitness_function


class CandidateSelector:
    """
    Select best candidates based on fitness scores.
    
    The selector:
    1. Calculates fitness for all candidates
    2. Ranks candidates by fitness (lower = better)
    3. Applies deterministic tie-breaking (lexicographic by ID)
    4. Selects top N candidates
    5. Handles empty and entirely invalid populations
    
    Example:
        >>> selector = CandidateSelector()
        >>> results = [result1, result2, result3]
        >>> 
        >>> # Select best candidate
        >>> selection = selector.select_best(results, n_select=1)
        >>> best_id = selection.selected_candidates[0]
        >>> best_fitness = selection.fitness_scores[best_id]
        >>> 
        >>> # Select top 3
        >>> selection = selector.select_best(results, n_select=3)
    """
    
    def __init__(
        self,
        fitness_function: Optional[FitnessFunction] = None
    ):
        """
        Initialize the selector.
        
        Args:
            fitness_function: Fitness function for scoring
                             (creates default strict fitness if None)
        """
        self.fitness_function = fitness_function or create_fitness_function("strict")
    
    def select_best(
        self,
        results: List[BenchmarkResult],
        n_select: int = 1
    ) -> SelectionResult:
        """
        Select best N candidates from benchmark results.
        
        Args:
            results: List of benchmark results to select from
            n_select: Number of candidates to select
            
        Returns:
            SelectionResult with selected candidates and rankings
            
        Raises:
            ValueError: If n_select is invalid or results is empty
        """
        if not results:
            raise ValueError("Cannot select from empty results list")
        
        if n_select < 1:
            raise ValueError(f"n_select must be >= 1, got {n_select}")
        
        if n_select > len(results):
            n_select = len(results)
        
        # Calculate fitness scores
        fitness_scores = self.fitness_function.calculate_batch(results)
        
        # Rank candidates (lower fitness = better rank)
        # Deterministic tie-breaking: lexicographic order by candidate_id
        ranked_candidates = sorted(
            results,
            key=lambda r: (fitness_scores[r.candidate_id], r.candidate_id)
        )
        
        # Select top N
        selected = ranked_candidates[:n_select]
        selected_ids = [r.candidate_id for r in selected]
        
        # Build rankings dictionary (1-indexed)
        rankings = {
            r.candidate_id: i + 1
            for i, r in enumerate(ranked_candidates)
        }
        
        # Build selection reason
        if all(f == float('inf') for f in fitness_scores.values()):
            reason = "All candidates failed evaluation"
        elif len(selected) == 1:
            best_fitness = fitness_scores[selected_ids[0]]
            reason = f"Selected best candidate with fitness {best_fitness:.2f}"
        else:
            best_fitness = fitness_scores[selected_ids[0]]
            worst_fitness = fitness_scores[selected_ids[-1]]
            reason = f"Selected top {len(selected)} candidates (fitness range: {best_fitness:.2f} to {worst_fitness:.2f})"
        
        return SelectionResult(
            selected_candidates=selected_ids,
            fitness_scores=fitness_scores,
            rankings=rankings,
            selection_reason=reason
        )
    
    def rank_candidates(
        self,
        results: List[BenchmarkResult]
    ) -> Dict[str, int]:
        """
        Rank all candidates without selection.
        
        Args:
            results: List of benchmark results
            
        Returns:
            Dictionary mapping candidate_id to rank (1=best)
        """
        if not results:
            return {}
        
        # Calculate fitness
        fitness_scores = self.fitness_function.calculate_batch(results)
        
        # Sort by fitness with deterministic tie-breaking
        ranked_candidates = sorted(
            results,
            key=lambda r: (fitness_scores[r.candidate_id], r.candidate_id)
        )
        
        # Build rankings (1-indexed)
        return {
            r.candidate_id: i + 1
            for i, r in enumerate(ranked_candidates)
        }
    
    def __repr__(self) -> str:
        return f"CandidateSelector(fitness={self.fitness_function})"


def select_elite(
    results: List[BenchmarkResult],
    elite_fraction: float = 0.2,
    min_elite: int = 1,
    max_elite: int = 5
) -> SelectionResult:
    """
    Select elite candidates (top fraction of population).
    
    Convenience function for elitism in evolutionary algorithms.
    
    Args:
        results: List of benchmark results
        elite_fraction: Fraction of population to select (0.0-1.0)
        min_elite: Minimum number to select
        max_elite: Maximum number to select
        
    Returns:
        SelectionResult with elite candidates
        
    Example:
        >>> # Select top 20% (at least 1, at most 5)
        >>> elite = select_elite(all_results, elite_fraction=0.2)
    """
    if not (0.0 <= elite_fraction <= 1.0):
        raise ValueError(f"elite_fraction must be in [0, 1], got {elite_fraction}")
    
    if not results:
        raise ValueError("Cannot select from empty results list")
    
    # Calculate number to select
    n_elite = max(min_elite, int(len(results) * elite_fraction))
    n_elite = min(n_elite, max_elite, len(results))
    
    # Use selector
    selector = CandidateSelector()
    return selector.select_best(results, n_select=n_elite)
