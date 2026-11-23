"""Offline oracles for benchmark inputs, accounting, reporting and split guards."""
from copy import deepcopy
from dataclasses import asdict, replace
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from engine.evaluation import fleet_benchmark as benchmark
from engine.evaluation.fleet_benchmark import BenchmarkConfig, METHODS, run_case, run_method
from engine.evaluation.fleet_dataset import (Case, DRIVERS, DISTRIBUTIONS, SIZES, SPLITS,
                                            case_by_id, cases, catalog_fingerprint)
from engine.evaluation.fleet_reporting import improvement, summarize, tied, write_reports
from engine.routing import FleetProblem, validate_fleet_solution
from engine.routing.construction import legacy_angular_round_robin
from engine.routing.search import SearchConfig
from scripts.run_fleet_benchmark import main


def small_problem(directed=False):
    # Cycle 0->1->2->3->0 costs 3+5+2+6=16; reverse differs when directed.
    return FleetProblem(depot_id=0, stop_ids=(1, 2, 3), num_drivers=1,
        distance_matrix=((0, 3, 4, 6), (8 if directed else 3, 0, 5, 7),
                         (4, 9 if directed else 5, 0, 2), (6, 7, 2, 0)),
        distance_units="map_units", directed=directed, coordinates=((0, 0), (3, 0), (0, 4), (0, 6)),
        coordinate_system="cartesian", matrix_provenance={"source": "provided" if directed else "euclidean"},
        instance_seed=0, search_seed=0)


def config(**kwargs):
    return BenchmarkConfig(**{"operations": 100_000, "seconds": 60.,
        "search": SearchConfig(ils_iterations=2, max_operator_calls=100), **kwargs})


def metric_row(method, cost, **updates):
    row = dict(method=method, total_distance=cost, longest_route_distance=cost,
               feasible=cost is not None, evaluation_failure=False, status="completed",
               termination_reason="completed", runtime_seconds=1., operations_used=2,
               operator_calls=1, accepted_moves=1, timeout=False, budget_exhausted=False)
    row.update(updates)
    return row


def metric_case(i, a, b, **updates):
    return {"case_id": str(i), "results": [metric_row("candidate", a, **updates), metric_row("baseline", b)]}


def pair(summary):
    return next(row for row in summary["paired"] if row["method"] == "candidate")


def test_full_dataset_coverage_and_disjoint_seeds():
    seen = set()
    for split in SPLITS:
        suite = cases(split)
        assert len(suite) == 360
        assert {c.stops for c in suite} == set(SIZES)
        assert {c.drivers for c in suite} == set(DRIVERS)
        assert {c.distribution for c in suite} == set(DISTRIBUTIONS)
        assert {c.directed for c in suite} == {True, False}
        assert {c.replicate for c in suite} == {0, 1, 2}
        seeds = {c.instance_seed for c in suite}
        assert len(seeds) == 360 and not seeds & seen
        seen |= seeds
    assert catalog_fingerprint() == catalog_fingerprint()


@pytest.mark.parametrize("distribution", DISTRIBUTIONS)
@pytest.mark.parametrize("directed", [False, True])
def test_generator_reproducible_and_matrix_semantics(distribution, directed):
    case = Case("development", 20, 3, distribution, directed, 0)
    p, q = case.problem(), case_by_id(case.id).problem()
    assert p == q and p.fingerprint == q.fingerprint
    assert p.instance_seed == case.instance_seed and p.search_seed == 0
    assert p.directed is directed and p.n_stops == 20 and p.num_drivers == 3
    assert p.matrix_provenance.source == ("provided" if directed else "euclidean")
    assert any(p.distance_matrix[i][j] != p.distance_matrix[j][i]
               for i in range(21) for j in range(21)) is directed
    assert case.problem(7).fingerprint == p.fingerprint
    with pytest.raises(ValueError):
        p.matrix_array()[0, 1] = 0


def test_all_methods_receive_identical_object(monkeypatch):
    original = benchmark.run_method
    seen = []
    def observing(problem, method, cfg):
        seen.append(problem)
        return original(problem, method, cfg)
    monkeypatch.setattr(benchmark, "run_method", observing)
    case = cases(profile="smoke")[0]
    record = run_case(case, config(operations=20_000))
    assert len(seen) == len(METHODS)
    assert all(problem is seen[0] for problem in seen)
    assert all(row["problem_fingerprint"] == record["problem_fingerprint"] for row in record["results"])
    assert all(row["matrix_fingerprint"] == record["matrix_fingerprint"] for row in record["results"])
    assert FleetProblem.model_validate(record["problem"]).fingerprint == record["problem_fingerprint"]


@pytest.mark.parametrize("method", METHODS + ("random_config_search",))
@pytest.mark.parametrize("directed", [False, True])
def test_determinism_independent_cost_feasibility_and_no_mutation(method, directed):
    p, cfg = small_problem(directed), config(random_trials=2)
    original = p.model_dump()
    a, b = run_method(p, method, cfg), run_method(p, method, cfg)
    assert p.model_dump() == original
    for row in (a, b):
        row.pop("runtime_seconds")
        for trial in row["random_trials"]:
            trial.pop("runtime_seconds")
    assert a == b
    if method == "sweep" and directed:
        assert a["status"] == "not_applicable" and a["total_distance"] is None
    else:
        assert a["feasible"] and not a["evaluation_failure"]
        assert a["operations_used"] <= cfg.operations
        assert a["final_method"] is not None
        if method == "hybrid_vnd":
            assert a["ils_iterations"] == 0
        if method == "hybrid_ils":
            assert a["ils_iterations"] == 2
        assert validate_fleet_solution(p, a["routes"]).total_distance == a["total_distance"]
        # Separate edge-sum oracle, not solver metric fields.
        assert sum(p.distance_matrix[x][y] for route in a["routes"]
                   for x, y in zip(route, route[1:])) == a["total_distance"]


@pytest.mark.parametrize("directed", [False, True])
@pytest.mark.parametrize("method,legacy", [("historical_nn", "nearest_neighbor"), ("historical_nn_2opt", "2opt")])
def test_completed_historical_baselines_are_unchanged(directed, method, legacy):
    p = small_problem(directed)
    row = run_method(p, method, config())
    previous = legacy_angular_round_robin(p, method=legacy)
    assert row["status"] == "completed"
    assert row["routes"] == previous.routes and row["total_distance"] == previous.total_distance


@pytest.mark.parametrize("method", METHODS)
def test_zero_budget_runs_are_recorded_not_silently_dropped(method):
    result = run_method(small_problem(), method, config(operations=0))
    assert result["status"] == "incomplete"
    assert result["budget_exhausted"] and result["operations_used"] == 0
    assert result["termination_reason"] == "operation_budget"
    if method.startswith("hybrid") or method == "constructor_portfolio":
        assert result["feasible"]
    else:
        assert result["total_distance"] is None


def test_timeout_and_seed_zero():
    result = run_method(small_problem(), "hybrid_ils", config(seconds=0))
    assert result["timeout"] and result["feasible"] and result["status"] == "incomplete"
    assert result["search_seed"] == 0


def test_exception_and_invalid_plan_are_failures(monkeypatch):
    def fail(*args, **kwargs):
        raise RuntimeError("private provider error should never enter a report")
    monkeypatch.setattr(benchmark, "cheapest_insertion", fail)
    result = run_method(small_problem(), "cheapest_insertion", config())
    assert result["status"] == "failed" and result["evaluation_failure"]
    assert result["error_type"] == "RuntimeError"
    assert "private" not in json.dumps(result)
    # Supply a real dataclass work record so failure is independent validation.
    from engine.routing.trusted import WorkCounters
    monkeypatch.setattr(benchmark, "cheapest_insertion", lambda *a, **k: SimpleNamespace(
        routes=((0, 1, 0),), work=WorkCounters()))
    result = run_method(small_problem(), "cheapest_insertion", config())
    assert result["termination_reason"] == "invalid_solution"
    assert result["evaluation_failure"] and not result["feasible"]


def test_false_reported_cost_is_independently_recomputed(monkeypatch):
    from engine.routing.trusted import WorkCounters
    monkeypatch.setattr(benchmark, "cheapest_insertion", lambda *a, **k: SimpleNamespace(
        routes=((0, 1, 2, 3, 0),), total_distance=-999, work=WorkCounters()))
    row = run_method(small_problem(True), "cheapest_insertion", config())
    assert row["total_distance"] == 16 and row["longest_route_distance"] == 16


def test_paired_arithmetic_and_regressions():
    records = [metric_case(0, 80, 100), metric_case(1, 110, 100), metric_case(2, 50, 50)]
    summary = summarize(records)
    result = pair(summary)
    assert (result["wins"], result["ties"], result["losses"]) == (1, 1, 1)
    assert result["improvement_percent"]["mean"] == pytest.approx(10/3)
    assert result["improvement_percent"]["median"] == 0
    assert result["worst_regression_percent"] == 10
    assert result["worst_defined_pair_case"] == "1"
    assert records[0]["results"][1]["gap_to_best_observed_percent"] == 25
    assert result["improvement_percent"]["sample_sd"] > 0
    assert result == pair(summarize(deepcopy(records)))


def test_zero_ties_and_undefined_percentages_are_not_improvements():
    records = [metric_case(0, 0, 0), metric_case(1, 5, 0), metric_case(2, 0, 10)]
    result = pair(summarize(records))
    assert (result["wins"], result["ties"], result["losses"]) == (1, 1, 1)
    assert result["undefined_percentage_pairs"] == 1
    assert result["zero_reference_losses"] == 1 and result["worst_regression_percent"] is None
    assert result["worst_absolute_regression"] == 5
    assert improvement(0, 5) is None and improvement(0, 0) == 0 and improvement(10, 0) == 100
    assert records[1]["results"][0]["gap_to_best_observed_percent"] is None
    assert tied(1., 1.+1e-10) and not tied(1., 1.+1e-7)
    json.dumps(records, allow_nan=False)


def test_failed_incomplete_missing_pairs_and_completion_rates():
    records = [metric_case(0, 80, 100, status="incomplete", budget_exhausted=True),
               metric_case(1, 1, 100, status="failed", evaluation_failure=True),
               metric_case(2, None, 100, status="incomplete", timeout=True, budget_exhausted=True)]
    summary = summarize(records)
    p = pair(summary)
    assert (p["valid_pairs"], p["unavailable_pairs"], p["incomplete_pairs"], p["complete_pairs"]) == (0, 3, 0, 0)
    assert p["improvement_percent"]["mean"] is None
    assert p["excluded_pairs"] == {"missing": 0, "failed": 1, "inapplicable": 0, "incomplete": 2, "no_feasible_result": 0}
    assert p["complete_pairs_improvement_percent"]["mean"] is None
    assert records[1]["best_observed_distance"] == 100
    assert records[1]["results"][0]["gap_to_best_observed_percent"] is None
    m = summary["methods"]["candidate"]
    assert m["evaluation_failure_rate"] == m["timeout_rate"] == m["no_feasible_result_rate"] == pytest.approx(1/3)
    assert m["budget_exhaustion_rate"] == pytest.approx(2/3)


def test_report_formats_and_overwrite_protection(tmp_path):
    record = run_case(cases(profile="smoke")[0], config(operations=1000))
    bundle = {"split": "development", "profile": "single_case", "cases": [record],
              "protocol": {"protocol_fingerprint": "test", "config": asdict(config())}}
    output = tmp_path / "report"
    write_reports(bundle, output)
    restored = json.loads((output / "results.json").read_text())
    assert len(restored["cases"][0]["results"]) == 7
    assert len((output / "results.csv").read_text().splitlines()) == 8
    text = (output / "report.md").read_text()
    assert "not a proven optimum" in text and "Incomplete feasible incumbents" in text
    assert record["case_id"] in text and "Worst regression" in text
    with pytest.raises(FileExistsError):
        write_reports(bundle, output)


def test_case_rerun_is_reproducible():
    case = cases()[0]
    a, b = run_case(case, config(operations=1000)), run_case(case_by_id(case.id), config(operations=1000))
    for record in (a, b):
        for row in record["results"]:
            row.pop("runtime_seconds")
    assert a == b


@pytest.mark.parametrize("args", [
    ["--split", "heldout"], ["--split", "heldout", "--acknowledge-heldout"],
    ["--case", cases("heldout")[0].id], ["--operations", "-1"], ["--seconds", "nan"],
    ["--search-seed", "1.5"], ["--random-trials", "9"], ["--case", "missing"]])
def test_cli_invalid_or_unregistered_runs_fail_before_evaluation(args, monkeypatch):
    monkeypatch.setattr("scripts.run_fleet_benchmark.run_case", lambda *a: pytest.fail("must not execute"))
    with pytest.raises(SystemExit) as exc:
        main(args)
    assert exc.value.code == 2


def test_protocol_freeze_heldout_guards_and_rerun(tmp_path, monkeypatch):
    path = tmp_path / "protocol.json"
    assert main(["--freeze-protocol", str(path), "--operations", "0", "--search-seed", "0"]) == 0
    frozen = json.loads(path.read_text())
    assert frozen["config"]["search_seed"] == 0
    for args in (["--freeze-protocol", str(path)],
                 ["--protocol", str(path), "--operations", "1"]):
        with pytest.raises(SystemExit):
            main(args)
    # A single explicitly acknowledged held-out case, with the frozen budget.
    case = cases("heldout")[0]
    output = tmp_path / "heldout"
    assert main(["--protocol", str(path), "--split", "heldout", "--acknowledge-heldout",
                 "--case", case.id, "--output", str(output)]) == 0
    result = json.loads((output / "results.json").read_text())
    assert result["protocol"] == frozen and result["profile"] == "single_case"
    assert result["cases"][0]["problem"]["instance_seed"] == case.instance_seed
    forged = deepcopy(frozen)
    forged["config"]["operations"] = 10
    with pytest.raises(ValueError, match="fingerprint"):
        benchmark.verify_protocol(forged, Path(__file__).resolve().parents[2])
    monkeypatch.setattr(benchmark, "source_fingerprint", lambda root: "changed")
    with pytest.raises(ValueError, match="software"):
        benchmark.verify_protocol(frozen, Path(__file__).resolve().parents[2])


def test_random_control_allocation_and_recorded_configs():
    cfg = config(operations=1001, random_trials=3)
    row = run_method(small_problem(True), "random_config_search", cfg)
    assert row["operations_used"] <= 1001
    assert len(row["random_trials"]) == 3
    assert all(t["operations"] <= 333 for t in row["random_trials"])
    assert all(SearchConfig(**t["config"]) for t in row["random_trials"])
    assert row["feasible"] and not row["evaluation_failure"]


def test_hybrid_partial_failures_remain_failures_even_with_feasible_plan(monkeypatch):
    p, cfg = small_problem(True), config()
    result = benchmark.solve_hybrid(p, config=cfg.search, operation_budget=1000, time_limit_seconds=60)
    monkeypatch.setattr(benchmark, "solve_hybrid", lambda *a, **k: replace(
        result, errors=("cheapest_insertion: ValueError",), status="stopped"))
    row = run_method(p, "hybrid_ils", cfg)
    assert row["feasible"] and row["evaluation_failure"] and row["status"] == "failed"
    assert row["errors"] == ["cheapest_insertion: ValueError"]


def test_random_control_deadline_without_trials_is_incomplete():
    row = run_method(small_problem(), "random_config_search", config(seconds=0, random_trials=2))
    assert row["timeout"] and row["budget_exhausted"] and row["status"] == "incomplete"
    assert row["random_trials"] == [] and row["total_distance"] is None


def test_unknown_method_and_mismatched_seed_are_rejected():
    with pytest.raises(ValueError, match="method"):
        run_method(small_problem(), "nonexistent", config())
    with pytest.raises(ValueError, match="seed"):
        run_method(small_problem(), "hybrid_vnd", config(search_seed=1))


def test_smoke_profile_coverage_and_unknown_case_rejection():
    suite = cases(profile="smoke")
    assert len(suite) == 12
    assert {c.stops for c in suite} == set(SIZES)
    assert {c.drivers for c in suite} == set(DRIVERS)
    assert {c.distribution for c in suite} == set(DISTRIBUTIONS)
    assert {c.directed for c in suite} == {True, False}
    assert len({c.instance_seed for c in suite}) == 12
    with pytest.raises(ValueError):
        case_by_id("unknown")


def test_all_failed_quality_and_inapplicable_denominators():
    records = [metric_case(0, None, None, status="failed", evaluation_failure=True)]
    records[0]["results"][1].update(status="not_applicable")
    summary = summarize(records)
    assert records[0]["best_observed_distance"] is None
    assert pair(summary)["valid_pairs"] == 0
    assert pair(summary)["improvement_percent"]["mean_ci95"] is None
    assert summary["methods"]["baseline"]["attempted"] == 0
    assert summary["methods"]["baseline"]["timeout_rate"] is None
