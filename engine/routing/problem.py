"""Version 1 fleet problem contract. Matrix order is depot, then ordered stop IDs."""
import hashlib
import json
import math
from typing import Literal

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, StrictInt, model_validator


class FrozenModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)


class MatrixProvenance(FrozenModel):
    source: Literal["euclidean", "road", "provided"]
    provider: str | None = None
    dataset_version: str | None = None


class FleetObjective(FrozenModel):
    primary: Literal["total_distance"] = "total_distance"
    direction: Literal["minimize"] = "minimize"
    # A reported diagnostic, never a hidden weighted objective or tie-break.
    secondary_metric: Literal["longest_route_distance"] | None = "longest_route_distance"


class WorkloadConstraints(FrozenModel):
    """Bounds indexed by driver slot; v1 permits only balanced stop counts."""
    policy: Literal["balanced_stop_count"] = "balanced_stop_count"
    minimum_stops: tuple[StrictInt, ...]
    maximum_stops: tuple[StrictInt, ...]


class FleetProblem(FrozenModel):
    schema_version: Literal["fleet-problem/v1"] = "fleet-problem/v1"
    depot_id: StrictInt
    stop_ids: tuple[StrictInt, ...]
    distance_matrix: tuple[tuple[float, ...], ...]
    distance_units: Literal["map_units", "meters", "kilometers"]
    directed: bool
    num_drivers: StrictInt = Field(ge=1)
    workload: WorkloadConstraints | None = None
    coordinates: tuple[tuple[float, float], ...] | None = None
    coordinate_system: Literal["cartesian", "lon_lat"] | None = None
    matrix_provenance: MatrixProvenance
    objective: FleetObjective = Field(default_factory=FleetObjective)
    instance_seed: StrictInt | None = None
    search_seed: StrictInt | None = None

    @model_validator(mode="after")
    def validate_problem(self):
        ids = self.node_ids
        if len(set(ids)) != len(ids):
            raise ValueError("Depot and delivery stop IDs must be unique")
        size = len(ids)
        if len(self.distance_matrix) != size or any(len(row) != size for row in self.distance_matrix):
            raise ValueError("Distance matrix shape must match depot plus ordered stops")
        if any(not math.isfinite(v) or v < 0 for row in self.distance_matrix for v in row):
            raise ValueError("Distances must be finite and nonnegative")
        if not self.directed and any(self.distance_matrix[i][j] != self.distance_matrix[j][i]
                                     for i in range(size) for j in range(i)):
            raise ValueError("A symmetric problem must have a symmetric matrix")
        if (self.coordinates is None) != (self.coordinate_system is None):
            raise ValueError("Coordinates and their coordinate system must be supplied together")
        if self.coordinates is not None:
            if len(self.coordinates) != size:
                raise ValueError("Coordinates must follow matrix node order")
            if self.coordinate_system == "lon_lat" and any(
                    abs(lon) > 180 or abs(lat) > 90 for lon, lat in self.coordinates):
                raise ValueError("Geographic coordinates must be longitude/latitude pairs")
        lower, remainder = divmod(self.n_stops, self.num_drivers)
        upper = lower + bool(remainder)
        if self.workload is None:
            object.__setattr__(self, "workload", WorkloadConstraints(
                minimum_stops=(lower,) * self.num_drivers,
                maximum_stops=(upper,) * self.num_drivers))
        bounds = self.workload
        if (len(bounds.minimum_stops) != self.num_drivers
                or len(bounds.maximum_stops) != self.num_drivers
                or any(not lower <= lo <= hi <= upper
                       for lo, hi in zip(bounds.minimum_stops, bounds.maximum_stops))
                or sum(bounds.minimum_stops) > self.n_stops
                or sum(bounds.maximum_stops) < self.n_stops):
            raise ValueError("Workload bounds must be feasible within floor(n/k)..ceil(n/k)")
        return self

    @property
    def node_ids(self):
        return (self.depot_id,) + self.stop_ids

    @property
    def n_stops(self):
        return len(self.stop_ids)

    @property
    def seed(self):
        """Legacy evaluation record compatibility; None is represented by -1."""
        return self.instance_seed if self.instance_seed is not None else -1

    @property
    def matrix_fingerprint(self):
        return self._digest(self.distance_matrix)

    @property
    def fingerprint(self):
        # Search randomness is run metadata, not a different routing problem.
        return self._digest(self.model_dump(mode="json", exclude={"search_seed"}))

    @staticmethod
    def _digest(value):
        return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                         allow_nan=False).encode("utf-8")).hexdigest()

    def matrix_array(self):
        """Read-only NumPy view backed by immutable bytes (cannot re-enable writes)."""
        size = self.n_stops + 1
        return np.frombuffer(np.asarray(self.distance_matrix, dtype=np.float64).tobytes(),
                             dtype=np.float64).reshape(size, size)
