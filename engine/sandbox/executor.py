"""
Controlled execution of validated candidate heuristics.

Executes heuristics in a restricted namespace with timeout enforcement.
"""

import numpy as np
import time
import ast
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any, Dict, Optional, Callable
from contextlib import contextmanager

from .models import CandidateHeuristic, ExecutionResult, ExecutionStatus
from engine.heuristics import HeuristicContext, HeuristicResult


class TimeoutException(Exception):
    """Raised when execution exceeds timeout."""
    pass


class HeuristicExecutor:
    """Bounded subprocess interpreter for the explicitly supported scoring language.

    Isolation is process/resource isolation, not permission to run arbitrary
    Python. Full Python/NumPy execution is deliberately unavailable.
    """

    def __init__(self, timeout: float = 5.0):
        """
        Initialize the executor.
        
        Args:
            timeout: Maximum execution time in seconds (default: 5.0)
        """
        self.timeout = timeout
    
    def execute(self, candidate: CandidateHeuristic, context: HeuristicContext) -> ExecutionResult:
        """Interpret a validated scoring AST in a bounded, disposable subprocess.

        No generated Python is compiled/executed. Unsupported language features
        and missing OS resource limits fail closed. This is not an OS-level
        filesystem/network sandbox for arbitrary Python.
        """
        from .validator import HeuristicValidator
        started = time.monotonic()
        try:
            ast.parse(candidate.source_code)
        except SyntaxError as exc:
            return ExecutionResult(status=ExecutionStatus.SYNTAX_ERROR, error=f"Syntax error: {exc}")
        validation = HeuristicValidator().validate(candidate)
        if not validation.is_valid:
            return ExecutionResult(status=ExecutionStatus.RUNTIME_ERROR,
                                   error="Validation failed: " + "; ".join(validation.errors))
        payload = json.dumps({
            'source': candidate.source_code, 'name': candidate.function_name,
            'context': {'current_location': context.current_location,
                        'candidate_stops': context.candidate_stops,
                        'partial_route': context.partial_route,
                        'distance_matrix': context.distance_matrix.tolist()},
        }, allow_nan=False)
        if len(payload.encode('utf-8')) > 2_000_000:
            return ExecutionResult(status=ExecutionStatus.RUNTIME_ERROR, error="Candidate input exceeds limit")
        # Do not inherit credentials, proxy configuration, PYTHONPATH, or user
        # site initialization. Windows needs its system directory only.
        environment = {'SYSTEMROOT': os.environ.get('SYSTEMROOT', 'C:\\Windows')} if os.name == 'nt' else {}
        process = None
        try:
            process = subprocess.Popen(
                [sys.executable, '-I', '-S', '-B', str(Path(__file__).with_name('worker.py').resolve()), str(self.timeout)],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                text=True, encoding='utf-8', env=environment,
                cwd=str(Path(sys.executable).parent), close_fds=True,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
            )
            try:
                output, _ = process.communicate(payload, timeout=self.timeout)
            except subprocess.TimeoutExpired:
                process.kill()
                process.communicate()
                return ExecutionResult(status=ExecutionStatus.TIMEOUT,
                    error=f"Execution timeout ({self.timeout}s); worker terminated and reaped",
                    execution_time=time.monotonic() - started,
                    details={'pid': process.pid, 'reaped': process.poll() is not None})
            if process.returncode != 0:
                raise RuntimeError('Worker exited without a result (resource limit or worker failure)')
            result = json.loads(output)
            if result.get('status') == 'success':
                result['output']['scores'] = {int(k): v for k, v in result['output']['scores'].items()}
                error = self._validate_output(result['output'], context)
                if error:
                    raise ValueError(error)
            result['execution_time'] = time.monotonic() - started
            result.setdefault('details', {})['reaped'] = process.poll() is not None
            return ExecutionResult(**result)
        except Exception as exc:
            return ExecutionResult(status=ExecutionStatus.RUNTIME_ERROR,
                error=f"Isolated execution failed: {type(exc).__name__}: {exc}",
                execution_time=time.monotonic() - started)
        finally:
            if process is not None and process.poll() is None:
                process.kill()
                process.wait()

    def execute_to_heuristic_result(
        self,
        candidate: CandidateHeuristic,
        context: HeuristicContext
    ) -> HeuristicResult:
        """
        Execute candidate and convert output to HeuristicResult.
        
        This is a convenience method that wraps execute() and converts
        the output to HeuristicResult, raising appropriate exceptions
        on failure.
        
        Args:
            candidate: Candidate heuristic to execute
            context: Heuristic context
            
        Returns:
            HeuristicResult with scores
            
        Raises:
            ValueError: If execution fails or output is invalid
            TimeoutError: If execution times out
        """
        result = self.execute(candidate, context)
        
        if not result.is_success:
            if result.status == ExecutionStatus.TIMEOUT:
                raise TimeoutError(f"Execution timeout: {result.error}")
            else:
                raise ValueError(f"Execution failed: {result.error}")
        
        # Convert output to HeuristicResult
        output = result.output
        
        # Handle different output formats
        if isinstance(output, HeuristicResult):
            return output
        elif isinstance(output, dict):
            # Try to extract scores
            if 'scores' in output:
                try:
                    return HeuristicResult(scores=output['scores'])
                except Exception as e:
                    raise ValueError(f"Invalid scores in output dict: {e}")
            else:
                raise ValueError("Output dict must contain 'scores' key")
        else:
            raise ValueError(
                f"Invalid output type: {type(output)}. "
                f"Expected HeuristicResult or dict with 'scores'"
            )
    
    def _validate_output(self, output: Any, context: HeuristicContext) -> Optional[str]:
        """
        Validate the output from the heuristic.
        
        Args:
            output: Output from heuristic function
            context: Input context (for validating score count)
            
        Returns:
            Error message if invalid, None if valid
        """
        # Check output type
        if output is None:
            return "Function returned None"
        
        # Accept HeuristicResult or dict with scores
        if isinstance(output, HeuristicResult):
            scores = output.scores
        elif isinstance(output, dict):
            if 'scores' not in output:
                return "Output dict must contain 'scores' key"
            scores = output['scores']
        else:
            return f"Invalid output type: {type(output)}. Expected HeuristicResult or dict"
        
        # Validate scores is a dict
        if not isinstance(scores, dict):
            return f"Scores must be a dict, got {type(scores)}"
        
        # Check score count
        expected_stops = set(context.candidate_stops)
        actual_stops = set(scores.keys())
        
        if expected_stops != actual_stops:
            missing = expected_stops - actual_stops
            extra = actual_stops - expected_stops
            parts = []
            if missing:
                parts.append(f"missing {sorted(missing)}")
            if extra:
                parts.append(f"extra {sorted(extra)}")
            return f"Score count mismatch: {', '.join(parts)}"
        
        # Validate all scores are finite numbers
        for stop, score in scores.items():
            if not isinstance(score, (int, float, np.number)):
                return f"Score for stop {stop} is not numeric: {type(score)}"
            if not np.isfinite(score):
                return f"Score for stop {stop} is not finite: {score}"
        
        return None
