"""
Controlled execution of validated candidate heuristics.

Executes heuristics in a restricted namespace with timeout enforcement.
"""

import numpy as np
import signal
import time
from typing import Any, Dict, Optional, Callable
from contextlib import contextmanager

from .models import CandidateHeuristic, ExecutionResult, ExecutionStatus
from engine.heuristics import HeuristicContext, HeuristicResult


class TimeoutException(Exception):
    """Raised when execution exceeds timeout."""
    pass


def _timeout_handler(signum, frame):
    """Signal handler for timeout."""
    raise TimeoutException("Execution timeout")


class HeuristicExecutor:
    """
    Executes validated candidate heuristics in a controlled environment.
    
    Safety Features:
        - Restricted namespace (minimal built-ins)
        - Timeout enforcement
        - No access to filesystem, network, or environment
        - Structured error handling
    
    Security Limitations:
        This is NOT a secure sandbox. It provides defense-in-depth for
        an academic demo by:
        - Restricting available built-ins
        - Enforcing timeouts
        - Running validated code only
        
        Do NOT:
        - Execute truly malicious code
        - Run on public servers
        - Pass secrets to candidate code
        - Claim this is production-ready
    
    Example:
        >>> executor = HeuristicExecutor(timeout=5.0)
        >>> result = executor.execute(candidate, context)
        >>> if result.is_success:
        ...     heuristic_result = result.output
    """
    
    # Minimal set of built-in functions
    SAFE_BUILTINS = {
        'abs': abs,
        'min': min,
        'max': max,
        'sum': sum,
        'len': len,
        'range': range,
        'enumerate': enumerate,
        'zip': zip,
        'sorted': sorted,
        'float': float,
        'int': int,
        'round': round,
        'list': list,
        'dict': dict,
        'tuple': tuple,
        'set': set,
        'bool': bool,
        'str': str,
        'all': all,
        'any': any,
        'True': True,
        'False': False,
        'None': None,
    }
    
    def __init__(self, timeout: float = 5.0):
        """
        Initialize the executor.
        
        Args:
            timeout: Maximum execution time in seconds (default: 5.0)
        """
        self.timeout = timeout
    
    def execute(
        self,
        candidate: CandidateHeuristic,
        context: HeuristicContext
    ) -> ExecutionResult:
        """
        Execute a validated candidate heuristic.
        
        Args:
            candidate: Candidate heuristic to execute (should be pre-validated)
            context: Heuristic context to pass to the function
            
        Returns:
            ExecutionResult with output or error
            
        Note:
            The candidate should be validated before calling this method.
            This method will attempt execution regardless, but may fail.
        """
        start_time = time.time()
        
        try:
            # Compile the code
            try:
                code_obj = compile(
                    candidate.source_code,
                    filename=f"<candidate:{candidate.function_name}>",
                    mode='exec'
                )
            except SyntaxError as e:
                return ExecutionResult(
                    status=ExecutionStatus.SYNTAX_ERROR,
                    error=f"Syntax error: {e}",
                    execution_time=time.time() - start_time
                )
            
            # Create restricted namespace
            namespace = self._create_namespace()
            
            # Execute code to define function (with timeout)
            try:
                with self._timeout_context(self.timeout):
                    exec(code_obj, namespace)
            except TimeoutException:
                return ExecutionResult(
                    status=ExecutionStatus.TIMEOUT,
                    error=f"Code definition exceeded timeout ({self.timeout}s)",
                    execution_time=time.time() - start_time
                )
            except Exception as e:
                return ExecutionResult(
                    status=ExecutionStatus.RUNTIME_ERROR,
                    error=f"Error defining function: {type(e).__name__}: {e}",
                    execution_time=time.time() - start_time
                )
            
            # Get the function
            if candidate.function_name not in namespace:
                return ExecutionResult(
                    status=ExecutionStatus.RUNTIME_ERROR,
                    error=f"Function '{candidate.function_name}' not found after execution",
                    execution_time=time.time() - start_time
                )
            
            func = namespace[candidate.function_name]
            
            # Call the function (with timeout)
            try:
                with self._timeout_context(self.timeout):
                    output = func(context)
            except TimeoutException:
                return ExecutionResult(
                    status=ExecutionStatus.TIMEOUT,
                    error=f"Execution exceeded timeout ({self.timeout}s)",
                    execution_time=time.time() - start_time
                )
            except Exception as e:
                return ExecutionResult(
                    status=ExecutionStatus.RUNTIME_ERROR,
                    error=f"{type(e).__name__}: {e}",
                    execution_time=time.time() - start_time
                )
            
            execution_time = time.time() - start_time
            
            # Validate output
            validation_error = self._validate_output(output, context)
            if validation_error:
                return ExecutionResult(
                    status=ExecutionStatus.INVALID_OUTPUT,
                    error=validation_error,
                    execution_time=execution_time
                )
            
            return ExecutionResult(
                status=ExecutionStatus.SUCCESS,
                output=output,
                execution_time=execution_time
            )
            
        except Exception as e:
            # Catch-all for unexpected errors
            return ExecutionResult(
                status=ExecutionStatus.RUNTIME_ERROR,
                error=f"Unexpected error: {type(e).__name__}: {e}",
                execution_time=time.time() - start_time
            )
    
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
    
    def _create_namespace(self) -> Dict[str, Any]:
        """
        Create a restricted namespace for code execution.
        
        Returns:
            Dictionary with safe built-ins and numpy
        """
        namespace = {
            '__builtins__': self.SAFE_BUILTINS,
            'np': np,  # Provide numpy
            'HeuristicResult': HeuristicResult,  # Allow returning HeuristicResult
        }
        return namespace
    
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
    
    @contextmanager
    def _timeout_context(self, seconds: float):
        """
        Context manager for timeout enforcement using signals.
        
        Args:
            seconds: Timeout in seconds
            
        Note:
            This uses SIGALRM which only works on Unix-like systems.
            On Windows, this will not enforce timeouts but will not error.
        """
        # Check if signal.SIGALRM is available (Unix only)
        if hasattr(signal, 'SIGALRM'):
            # Set up timeout
            old_handler = signal.signal(signal.SIGALRM, _timeout_handler)
            signal.alarm(int(seconds + 1))  # +1 for safety margin
            
            try:
                yield
            finally:
                # Cancel alarm and restore handler
                signal.alarm(0)
                signal.signal(signal.SIGALRM, old_handler)
        else:
            # Windows: no signal-based timeout, just run normally
            # In a production system, would use subprocess with timeout
            yield
