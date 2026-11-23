"""Versioned offline benchmark cases; never fetch roads or load environment files."""
from dataclasses import asdict, dataclass
import hashlib
import itertools
import json
import math
import random

from engine.routing.problem import FleetProblem

DATASET_VERSION = "fleet-benchmark/v1"
SPLITS = ("development", "validation", "heldout")
SIZES = (20, 50, 100, 200)
DRIVERS = (1, 2, 3, 5, 10)
DISTRIBUTIONS = ("uniform", "clustered", "mixed_density")
REPLICATES = (0, 1, 2)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode()).hexdigest()


@dataclass(frozen=True)
class Case:
    split: str
    stops: int
    drivers: int
    distribution: str
    directed: bool
    replicate: int

    def __post_init__(self):
        if (self.split not in SPLITS or self.stops not in SIZES or self.drivers not in DRIVERS
                or self.distribution not in DISTRIBUTIONS or type(self.directed) is not bool
                or type(self.replicate) is not int or self.replicate not in REPLICATES):
            raise ValueError("Unknown versioned benchmark case")

    @property
    def id(self):
        return (f"{self.split}-n{self.stops}-k{self.drivers}-{self.distribution}-"
                f"{'directed' if self.directed else 'symmetric'}-r{self.replicate}")

    @property
    def instance_seed(self):
        # Split membership is part of the seed, not a post-generation partition.
        return int(digest([DATASET_VERSION, asdict(self)])[:16], 16)

    def problem(self, search_seed=0):
        if type(search_seed) is not int:
            raise ValueError("search_seed must be an integer")
        rng = random.Random(self.instance_seed)
        centers = [(rng.uniform(15, 85), rng.uniform(15, 85)) for _ in range(4)]
        coordinates = [(50., 50.)]
        for _ in range(self.stops):
            clustered = self.distribution == "clustered" or (
                self.distribution == "mixed_density" and rng.random() < .7)
            if clustered:
                x, y = rng.choice(centers)
                coordinates.append((min(100., max(0., rng.gauss(x, 6))),
                                    min(100., max(0., rng.gauss(y, 6)))))
            else:
                coordinates.append((rng.uniform(0, 100), rng.uniform(0, 100)))
        matrix = [[0.] * len(coordinates) for _ in coordinates]
        for i, (x, y) in enumerate(coordinates):
            for j in range(i):
                a, b = coordinates[j]
                distance = math.hypot(x-a, y-b)
                matrix[i][j] = distance * (1 + rng.random() if self.directed else 1)
                matrix[j][i] = distance * (1 + rng.random() if self.directed else 1)
        return FleetProblem(depot_id=0, stop_ids=tuple(range(1, self.stops+1)),
            num_drivers=self.drivers, distance_matrix=matrix, distance_units="map_units",
            directed=self.directed, coordinates=coordinates, coordinate_system="cartesian",
            matrix_provenance={"source": "provided" if self.directed else "euclidean",
                               "provider": "offline_benchmark", "dataset_version": DATASET_VERSION},
            instance_seed=self.instance_seed, search_seed=search_seed)


def cases(split="development", profile="full"):
    if split not in SPLITS or profile not in ("full", "smoke"):
        raise ValueError("Unknown split or profile")
    if profile == "full":
        return tuple(Case(split, *values) for values in itertools.product(
            SIZES, DRIVERS, DISTRIBUTIONS, (False, True), REPLICATES))
    # Fixed 12-case coverage check, not a balanced statistical substitute for full.
    return tuple(Case(split, n, DRIVERS[(i*3+r) % len(DRIVERS)], DISTRIBUTIONS[r],
                      bool((i+r) % 2), r) for i, n in enumerate(SIZES) for r in REPLICATES)


def case_by_id(case_id):
    for split in SPLITS:
        for case in cases(split):
            if case.id == case_id:
                return case
    raise ValueError("Unknown benchmark case ID")


def catalog_fingerprint():
    return digest([asdict(case) for split in SPLITS for case in cases(split)])
