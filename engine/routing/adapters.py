"""Explicit bridges from coordinate-only legacy instances to fleet problems."""
import numpy as np

from engine.instances import compute_distance_matrix
from .problem import FleetProblem, MatrixProvenance


def problem_from_instance(instance, num_drivers=1, *, distance_matrix=None,
                          distance_units="map_units", provenance=None,
                          directed=None, coordinate_system="cartesian", search_seed=None):
    """Omitting a matrix explicitly selects the legacy synthetic Euclidean adapter.

    Road/provided matrices must be supplied; coordinates never replace them.
    """
    if (instance.depot.id != 0 or instance.n_stops != len(instance.stops)
            or [stop.id for stop in instance.stops] != list(range(1, instance.n_stops + 1))):
        raise ValueError("Legacy instances require depot 0 and sequential stop IDs 1..n")
    if distance_matrix is None:
        if distance_units != "map_units" or coordinate_system != "cartesian" or (
                provenance is not None and provenance.source != "euclidean"):
            raise ValueError("Road/provided problems require an explicit distance matrix")
        distance_matrix = compute_distance_matrix(instance.get_all_locations())
        provenance = MatrixProvenance(source="euclidean", provider="routeiq")
    matrix = np.asarray(distance_matrix, dtype=float)
    if matrix.ndim != 2:
        raise ValueError("Distance matrix must be two-dimensional")
    return FleetProblem(
        depot_id=instance.depot.id, stop_ids=tuple(stop.id for stop in instance.stops),
        distance_matrix=tuple(tuple(row) for row in matrix), distance_units=distance_units,
        directed=not np.array_equal(matrix, matrix.T) if directed is None else directed,
        num_drivers=num_drivers, matrix_provenance=provenance or MatrixProvenance(source="provided"),
        coordinates=tuple((point.x, point.y) for point in instance.get_all_locations()),
        coordinate_system=coordinate_system, instance_seed=instance.seed, search_seed=search_seed)


def problem_from_road_result(instance, num_drivers, road_result, *, search_seed=None):
    """Convert an already fetched road result, without network access or fallback."""
    if not road_result.success:
        raise ValueError("Cannot create a fleet problem from failed road routing")
    return problem_from_instance(
        instance, num_drivers, distance_matrix=road_result.distances,
        distance_units="meters", directed=True, coordinate_system="lon_lat",
        provenance=MatrixProvenance(source="road", provider=road_result.provider),
        search_seed=search_seed)
