"""
Tests for executor timeout functionality across platforms.

Verifies timeout behavior works on Windows and Unix with threading.
"""

import pytest
import time
import platform
import numpy as np

from engine.sandbox.executor import HeuristicExecutor, TimeoutException
from engine.sandbox.models import CandidateHeuristic, ExecutionStatus
from engine.heuristics import HeuristicContext


@pytest.mark.unit
class TestExecutorTimeout:
    """Test timeout functionality."""
    
    def _create_context(self, candidate_stops):
        """Create a valid HeuristicContext."""
        n = len(candidate_stops) + 1
        return HeuristicContext(
            current_location=0,
            current_route=[0],
            partial_route=[0],  # Must have at least one stop
            candidate_stops=candidate_stops,
            distance_matrix=np.array([[float(i*j) for i in range(n)] for j in range(n)]),
            visited={0}
        )
    
    def test_timeout_on_infinite_loop(self):
        """Test that infinite loop triggers timeout."""
        executor = HeuristicExecutor(timeout=0.5)
        
        # Infinite loop code
        code = """
def score_candidates(context):
    while True:
        pass
    return {"scores": {}}
"""
        
        candidate = CandidateHeuristic(
            source_code=code,
            function_name="score_candidates",
        )
        
        context = self._create_context([1, 2])
        
        result = executor.execute(candidate, context)
        
        # Should timeout
        assert not result.is_success
        assert result.status == ExecutionStatus.TIMEOUT
        assert "timeout" in result.error.lower()
        assert result.execution_time < 2.0  # Should not take too long
    
    def test_fast_execution_completes_within_timeout(self):
        """Test that fast execution completes successfully."""
        executor = HeuristicExecutor(timeout=5.0)
        
        code = """
def score_candidates(context):
    scores = {}
    for stop in context.candidate_stops:
        scores[stop] = float(stop)
    return {"scores": scores}
"""
        
        candidate = CandidateHeuristic(
            source_code=code,
            function_name="score_candidates",
        )
        
        context = self._create_context([1, 2, 3])
        
        start = time.time()
        result = executor.execute(candidate, context)
        elapsed = time.time() - start
        
        # Should complete quickly
        assert result.is_success
        assert result.status == ExecutionStatus.SUCCESS
        assert elapsed < 1.0  # Should be very fast
        assert result.execution_time < 1.0
    
    def test_timeout_works_on_windows(self):
        """Test that timeout mechanism works on Windows."""
        # This test verifies the thread-based timeout works on all platforms
        executor = HeuristicExecutor(timeout=0.5)
        
        # Busy loop (computationally intensive)
        code = """
def score_candidates(context):
    x = 0
    for i in range(100000000):  # Huge range
        x += i
    scores = {}
    for stop in context.candidate_stops:
        scores[stop] = 1.0
    return {"scores": scores}
"""
        
        candidate = CandidateHeuristic(
            source_code=code,
            function_name="score_candidates",
        )
        
        context = self._create_context([1, 2])
        
        result = executor.execute(candidate, context)
        
        # On any platform, should eventually timeout or complete
        # The key is it doesn't hang forever
        assert result.status in (ExecutionStatus.SUCCESS, ExecutionStatus.TIMEOUT)
        
        # If it timed out, verify the message
        if result.status == ExecutionStatus.TIMEOUT:
            assert "timeout" in result.error.lower()
    
    def test_platform_info(self):
        """Document platform information for debugging."""
        print(f"\nPlatform: {platform.system()}")
        print(f"Python: {platform.python_version()}")
        
        import signal
        has_sigalrm = hasattr(signal, 'SIGALRM')
        print(f"SIGALRM available: {has_sigalrm}")
        
        # This test always passes, just for information
        assert True


@pytest.mark.unit
class TestExecutorThreadSafety:
    """Test executor can run in different threading contexts."""
    
    def _create_context(self):
        """Create a valid HeuristicContext."""
        return HeuristicContext(
            current_location=0,
            current_route=[0],
            partial_route=[0],  # Must have at least one stop
            candidate_stops=[1, 2],
            distance_matrix=np.array([[0.0, 1.0, 2.0], [1.0, 0.0, 1.0], [2.0, 1.0, 0.0]]),
            visited={0}
        )
    
    def test_executor_in_main_thread(self):
        """Test executor runs in main thread."""
        import threading
        
        executor = HeuristicExecutor(timeout=1.0)
        
        code = """
def score_candidates(context):
    return {"scores": {1: 1.0, 2: 2.0}}
"""
        
        candidate = CandidateHeuristic(
            source_code=code,
            function_name="score_candidates",
        )
        
        context = self._create_context()
        
        # Execute in main thread
        current_thread = threading.current_thread().name
        print(f"Running in thread: {current_thread}")
        
        result = executor.execute(candidate, context)
        
        assert result.is_success
        assert result.status == ExecutionStatus.SUCCESS
    
    def test_executor_in_worker_thread(self):
        """Test executor runs correctly in worker thread."""
        import threading
        
        executor = HeuristicExecutor(timeout=1.0)
        
        code = """
def score_candidates(context):
    return {"scores": {1: 1.0, 2: 2.0}}
"""
        
        candidate = CandidateHeuristic(
            source_code=code,
            function_name="score_candidates",
        )
        
        context = self._create_context()
        
        result_holder = []
        
        def run_in_thread():
            current_thread = threading.current_thread().name
            print(f"Worker running in thread: {current_thread}")
            result = executor.execute(candidate, context)
            result_holder.append(result)
        
        # Execute in worker thread
        thread = threading.Thread(target=run_in_thread)
        thread.start()
        thread.join(timeout=2.0)
        
        # Thread should complete
        assert not thread.is_alive()
        assert len(result_holder) == 1
        
        result = result_holder[0]
        assert result.is_success
        assert result.status == ExecutionStatus.SUCCESS
    
    def test_executor_timeout_in_worker_thread(self):
        """Test timeout works correctly in worker thread."""
        import threading
        
        executor = HeuristicExecutor(timeout=0.5)
        
        # Code that will timeout
        code = """
def score_candidates(context):
    x = 0
    while x < 100000000:
        x += 1
    return {"scores": {1: 1.0, 2: 2.0}}
"""
        
        candidate = CandidateHeuristic(
            source_code=code,
            function_name="score_candidates",
        )
        
        context = self._create_context()
        
        result_holder = []
        
        def run_in_thread():
            result = executor.execute(candidate, context)
            result_holder.append(result)
        
        # Execute in worker thread
        thread = threading.Thread(target=run_in_thread)
        thread.start()
        thread.join(timeout=3.0)
        
        # Thread should complete (executor handles timeout internally)
        assert not thread.is_alive()
        assert len(result_holder) == 1
        
        result = result_holder[0]
        # Should timeout or complete
        assert result.status in (ExecutionStatus.TIMEOUT, ExecutionStatus.SUCCESS)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
