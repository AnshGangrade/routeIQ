"""
Manual test for OSRM road routing.

Run with: pytest tests/manual/test_osrm.py -v -s

This makes real network requests to the public OSRM demo server.
"""
import pytest
from engine.road import get_osrm_table, create_road_distance_matrix

# Berlin coordinates (lon, lat)
BERLIN_COORDINATES = [
    (13.388860, 52.517037),  # Berlin Central Station (depot)
    (13.397634, 52.529407),  # Gesundbrunnen
    (13.428555, 52.523219),  # Alexanderplatz
    (13.404954, 52.520008),  # Museum Island
]


@pytest.mark.skip(reason="Manual test - requires network access to OSRM")
def test_osrm_basic():
    """Test basic OSRM table request."""
    result = get_osrm_table(BERLIN_COORDINATES[:2])
    
    print(f"\nOSRM Response:")
    print(f"  Success: {result.success}")
    print(f"  Provider: {result.provider}")
    print(f"  Error: {result.error}")
    
    if result.success:
        print(f"  Distances shape: {len(result.distances)}x{len(result.distances[0])}")
        print(f"  Distance matrix:")
        for i, row in enumerate(result.distances):
            print(f"    {i}: {[f'{d:.0f}m' for d in row]}")
        
        # Check basic properties
        assert len(result.distances) == 2
        assert len(result.distances[0]) == 2
        assert result.distances[0][0] == 0  # Distance to self is 0
        assert result.distances[1][1] == 0
        assert result.distances[0][1] > 0   # Distance between points > 0
        assert result.distances[0][1] == result.distances[1][0]  # Symmetric


@pytest.mark.skip(reason="Manual test - requires network access to OSRM")
def test_osrm_full_matrix():
    """Test OSRM with 4 locations."""
    result = get_osrm_table(BERLIN_COORDINATES)
    
    print(f"\nFull OSRM Matrix:")
    print(f"  Success: {result.success}")
    
    if result.success:
        print(f"  Locations: {len(BERLIN_COORDINATES)}")
        print(f"  Distance matrix (meters):")
        for i, row in enumerate(result.distances):
            print(f"    {i}: {[f'{d:6.0f}' for d in row]}")
        
        print(f"  Duration matrix (seconds):")
        for i, row in enumerate(result.durations):
            print(f"    {i}: {[f'{d:6.1f}' for d in row]}")
        
        # Verify properties
        assert len(result.distances) == 4
        for i in range(4):
            assert result.distances[i][i] == 0  # Diagonal is zero
            for j in range(i + 1, 4):
                # Check symmetry
                assert abs(result.distances[i][j] - result.distances[j][i]) < 1


@pytest.mark.skip(reason="Manual test - requires network access to OSRM")
def test_road_distance_matrix_adapter():
    """Test the adapter that creates numpy distance matrix."""
    matrix, result = create_road_distance_matrix(BERLIN_COORDINATES)
    
    print(f"\nRoad Distance Matrix Adapter:")
    print(f"  Success: {result.success}")
    print(f"  Matrix shape: {matrix.shape}")
    
    if result.success:
        print(f"  Matrix (meters):")
        for i in range(matrix.shape[0]):
            print(f"    {i}: {[f'{matrix[i,j]:6.0f}' for j in range(matrix.shape[1])]}")
        
        # Check compatibility with routing algorithms
        assert matrix.shape == (4, 4)
        assert matrix[0, 0] == 0
        # Verify it's a proper distance matrix
        for i in range(4):
            for j in range(4):
                assert matrix[i, j] >= 0
                assert abs(matrix[i, j] - matrix[j, i]) < 1  # Nearly symmetric


@pytest.mark.skip(reason="Manual test - requires network access to OSRM")
def test_osrm_caching():
    """Test that repeated requests use cache."""
    # First request
    result1 = get_osrm_table(BERLIN_COORDINATES)
    assert not result1.cache_hit, "First request should not be cached"
    
    # Second request (same coordinates)
    result2 = get_osrm_table(BERLIN_COORDINATES)
    print(f"\nCache test:")
    print(f"  First request cache_hit: {result1.cache_hit}")
    print(f"  Second request cache_hit: {result2.cache_hit}")
    
    assert result2.cache_hit, "Second request should use cache"
    assert result1.distances == result2.distances


@pytest.mark.skip(reason="Manual test - requires network access to OSRM")
def test_osrm_error_handling():
    """Test error handling with invalid coordinates."""
    # Invalid coordinates (out of range)
    invalid_coords = [
        (200.0, 100.0),  # Invalid lon/lat
        (13.388860, 52.517037),
    ]
    
    result = get_osrm_table(invalid_coords)
    print(f"\nError handling test:")
    print(f"  Success: {result.success}")
    print(f"  Error: {result.error}")
    
    # Should fail gracefully
    assert not result.success
    assert result.error is not None


if __name__ == "__main__":
    # Run tests without skip markers for manual execution
    print("=" * 70)
    print("MANUAL OSRM TESTS")
    print("=" * 70)
    
    print("\n" + "=" * 70)
    print("Test 1: Basic OSRM Request (2 points)")
    print("=" * 70)
    try:
        result = get_osrm_table(BERLIN_COORDINATES[:2])
        print(f"✓ Success: {result.success}")
        if result.success:
            print(f"  Distance: {result.distances[0][1]:.0f} meters")
            print(f"  Duration: {result.durations[0][1]:.1f} seconds")
        else:
            print(f"✗ Error: {result.error}")
    except Exception as e:
        print(f"✗ Exception: {e}")
    
    print("\n" + "=" * 70)
    print("Test 2: Full Matrix (4 points)")
    print("=" * 70)
    try:
        result = get_osrm_table(BERLIN_COORDINATES)
        print(f"✓ Success: {result.success}")
        if result.success:
            print(f"  Matrix shape: {len(result.distances)}x{len(result.distances[0])}")
            print(f"  Sample distance [0→2]: {result.distances[0][2]:.0f} meters")
        else:
            print(f"✗ Error: {result.error}")
    except Exception as e:
        print(f"✗ Exception: {e}")
    
    print("\n" + "=" * 70)
    print("Test 3: Distance Matrix Adapter")
    print("=" * 70)
    try:
        matrix, result = create_road_distance_matrix(BERLIN_COORDINATES)
        print(f"✓ Success: {result.success}")
        if result.success:
            print(f"  NumPy shape: {matrix.shape}")
            print(f"  Matrix type: {type(matrix)}")
            print(f"  All diagonal zeros: {all(matrix[i,i] == 0 for i in range(4))}")
        else:
            print(f"✗ Error: {result.error}")
    except Exception as e:
        print(f"✗ Exception: {e}")
    
    print("\n" + "=" * 70)
