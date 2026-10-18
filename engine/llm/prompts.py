"""
Prompt engineering for LLM-guided heuristic generation.
"""

from typing import Optional, Dict, Any


def build_generation_prompt(
    iteration: int = 0,
    feedback: Optional[str] = None,
    best_score: Optional[float] = None,
    context: Optional[Dict[str, Any]] = None
) -> str:
    """
    Build a prompt for heuristic generation.
    
    The prompt explains:
    - The routing problem and heuristic role
    - Function signature and contract
    - Scoring convention (lower = better)
    - Available data structures
    - Safety restrictions (no imports, no I/O)
    - Context from previous iterations (if any)
    
    Args:
        iteration: Current iteration number (0 for initial)
        feedback: Feedback from previous iteration evaluation
        best_score: Best fitness score achieved so far
        context: Additional context (problem size, etc.)
        
    Returns:
        Formatted prompt string
    """
    context = context or {}
    
    # Base problem description
    prompt_parts = [
        "# Vehicle Routing Problem - Heuristic Generation",
        "",
        "You are tasked with generating a Python heuristic function for delivery route optimization.",
        "",
        "## Problem Context",
        "- Single depot with multiple delivery stops",
        "- Multiple drivers available",
        "- Routes constructed incrementally: start at depot, visit stops, return to depot",
        "- Goal: Minimize total distance traveled across all routes",
        "",
        "## Your Task",
        "Generate a Python function that scores candidate stops during route construction.",
        "The harness will call your function at each step to decide which unvisited stop to add next.",
        "",
        "## Function Signature",
        "```python",
        "def score_candidates(context):",
        '    """',
        "    Score unvisited stops to guide route construction.",
        "    ",
        "    Args:",
        "        context: HeuristicContext object with:",
        "            - current_location: int (current position index)",
        "            - candidate_stops: List[int] (unvisited stop indices)",
        "            - distance_matrix: np.ndarray (NxN distance matrix)",
        "            - partial_route: List[int] (route so far, starts with 0=depot)",
        "    ",
        "    Returns:",
        '        dict: {"scores": {stop_id: score}} or HeuristicResult object',
        "    ",
        "    Scoring Convention:",
        "        LOWER scores = MORE preferred candidates",
        "        The harness selects the stop with the LOWEST score",
        '    """',
        "    # Your implementation here",
        "    pass",
        "```",
        "",
        "## Available Context",
        "- `context.current_location`: Current position (0 = depot, 1..N = stops)",
        "- `context.candidate_stops`: List of unvisited stop indices",
        "- `context.distance_matrix`: NumPy array with all pairwise distances",
        "- `context.partial_route`: Route constructed so far",
        "",
        "## Scoring Strategy",
        "- Return one score per candidate stop",
        "- Lower scores indicate better (more preferred) candidates",
        "- Scores must be finite numbers (no NaN or infinity)",
        "- You can use: distance, position in route, geometric relationships, etc.",
        "",
        "## Available Tools",
        "- NumPy is available as `np`",
        "- Built-ins: abs, min, max, sum, len, range, enumerate, zip, sorted, float, int, round",
        "- Array operations: indexing, slicing, arithmetic, np.linalg.norm, etc.",
        "",
        "## Safety Restrictions",
        "- NO imports or from statements",
        "- NO file I/O (open, read, write)",
        "- NO network operations",
        "- NO exec, eval, compile, globals, locals",
        "- NO underscored names (_, __name__, etc.)",
        "- Keep the function under 100 lines",
        "",
    ]
    
    # Add iteration context
    if iteration > 0:
        prompt_parts.extend([
            f"## Iteration {iteration}",
            "",
        ])
        
        if best_score is not None:
            prompt_parts.extend([
                f"Best fitness so far: {best_score:.2f}",
                "",
            ])
        
        if feedback:
            prompt_parts.extend([
                "## Feedback from Previous Iteration",
                feedback,
                "",
                "Consider this feedback to improve your heuristic.",
                "",
            ])
    
    # Add problem-specific context
    if context:
        if "num_stops" in context:
            prompt_parts.append(f"Problem size: {context['num_stops']} delivery stops")
        if "num_drivers" in context:
            prompt_parts.append(f"Available drivers: {context['num_drivers']}")
        if context:
            prompt_parts.append("")
    
    # Closing instructions
    prompt_parts.extend([
        "## Output Format",
        "Provide ONLY the Python function definition.",
        "Do not include imports, test code, or explanations outside the function.",
        "The function must be named `score_candidates` and follow the signature above.",
        "",
        "Example (simple nearest-neighbor heuristic):",
        "```python",
        "def score_candidates(context):",
        "    scores = {}",
        "    for stop in context.candidate_stops:",
        "        scores[stop] = context.distance_matrix[context.current_location, stop]",
        '    return {"scores": scores}',
        "```",
        "",
        "Now generate your heuristic function:",
    ])
    
    return "\n".join(prompt_parts)


def build_feedback_prompt(
    fitness_score: float,
    comparison: Optional[str] = None,
    suggestions: Optional[str] = None
) -> str:
    """
    Build feedback message for the next iteration.
    
    Args:
        fitness_score: Fitness score achieved by this candidate
        comparison: Comparison with baselines (e.g., "15% worse than nearest neighbor")
        suggestions: Specific suggestions for improvement
        
    Returns:
        Formatted feedback string
    """
    parts = [
        f"Your heuristic achieved a fitness score of {fitness_score:.2f}.",
    ]
    
    if comparison:
        parts.append(comparison)
    
    if suggestions:
        parts.append("")
        parts.append("Suggestions for improvement:")
        parts.append(suggestions)
    
    return "\n".join(parts)


def build_refinement_prompt(
    source_code: str,
    feedback: str
) -> str:
    """
    Build a prompt for refining an existing heuristic.
    
    Args:
        source_code: Previous heuristic source code
        feedback: Feedback on what to improve
        
    Returns:
        Formatted prompt string
    """
    return f"""# Heuristic Refinement

The following heuristic needs improvement:

```python
{source_code}
```

## Feedback
{feedback}

## Task
Generate an IMPROVED version of this heuristic that addresses the feedback.
Maintain the same function signature: `score_candidates(context)`.
Return a dictionary with "scores" key mapping stop IDs to scores.

Remember: LOWER scores = MORE preferred candidates.

Provide ONLY the improved Python function definition:"""
