"""Independent offline cost/pairing audit; never runs or tunes a solver."""
import argparse
from collections import Counter
import csv
import json
import math
from pathlib import Path
import statistics
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine.routing import FleetProblem
from engine.evaluation.fleet_reporting import summarize, write_reports


def independent_cost(problem, routes):
    if len(routes) != problem.num_drivers:
        raise ValueError("Driver count mismatch")
    index = {node: i for i, node in enumerate(problem.node_ids)}
    stops, distances = [], []
    for driver, route in enumerate(routes):
        if len(route) < 2 or route[0] != problem.depot_id or route[-1] != problem.depot_id:
            raise ValueError("Depot endpoints missing")
        inner = route[1:-1]
        if (problem.depot_id in inner or any(type(node) is not int or node not in index for node in inner)
                or not problem.workload.minimum_stops[driver] <= len(inner) <= problem.workload.maximum_stops[driver]):
            raise ValueError("Invalid stops or workload")
        stops.extend(inner)
        cost = 0.
        if inner:
            for left, right in zip(route, route[1:]):
                cost += problem.distance_matrix[index[left]][index[right]]
        distances.append(cost)
    if Counter(stops) != Counter(problem.stop_ids):
        raise ValueError("Coverage mismatch")
    return sum(distances), max(distances, default=0.)


def audit_bundle(bundle):
    seen, records, attribution = set(), 0, []
    ils = {"runs": 0, "entered": 0, "iterations_attempted": 0, "iterations_completed": 0,
           "runs_with_completed_iteration": 0, "runs_with_new_global_best": 0,
           "global_best_updates": 0, "budget_exhausted_before_ils": 0,
           "budget_exhausted_during_ils": 0, "diagnostics_unavailable": 0}
    costs = []
    for case in bundle["cases"]:
        if case["case_id"] in seen:
            raise ValueError("Duplicate case")
        seen.add(case["case_id"])
        p = FleetProblem.model_validate(case["problem"])
        if p.fingerprint != case["problem_fingerprint"] or p.matrix_fingerprint != case["matrix_fingerprint"]:
            raise ValueError("Problem fingerprint mismatch")
        methods = {}
        for row in case["results"]:
            records += 1
            if row["method"] in methods:
                raise ValueError("Duplicate method")
            methods[row["method"]] = row
            if row["problem_fingerprint"] != p.fingerprint or row["matrix_fingerprint"] != p.matrix_fingerprint:
                raise ValueError("Methods did not share identical problem")
            if row["feasible"]:
                total, longest = independent_cost(p, row["routes"])
                if not math.isclose(total, row["total_distance"], rel_tol=1e-12, abs_tol=1e-9) or not math.isclose(longest, row["longest_route_distance"], rel_tol=1e-12, abs_tol=1e-9):
                    raise ValueError("Reported cost mismatch")
            elif row["status"] == "completed":
                raise ValueError("Completed run lacks feasible solution")
        base, vnd, extended = (methods.get(name) for name in ("historical_nn_2opt", "hybrid_vnd", "hybrid_ils"))
        if vnd and base and vnd["feasible"] and base["feasible"]:
            initial = vnd["initial_distance"]
            attribution.append({"case_id": case["case_id"], "stops": p.n_stops, "drivers": p.num_drivers,
                "eligible_completed_pair": vnd["status"] == base["status"] == "completed" and not vnd["evaluation_failure"] and not base["evaluation_failure"],
                "historical_2opt_distance": base["total_distance"], "initial_constructor_distance": initial,
                "final_vnd_distance": vnd["total_distance"], "construction_method": vnd["initial_method"],
                "construction_distance_gain": base["total_distance"]-initial,
                "vnd_distance_gain": initial-vnd["total_distance"],
                "historical_work": base["operations_used"], "vnd_work": vnd["operations_used"],
                "historical_runtime": base["runtime_seconds"], "vnd_runtime": vnd["runtime_seconds"]})
        if extended:
            ils["runs"] += 1
            diag = extended.get("search_diagnostics", [])
            if not diag:
                ils["diagnostics_unavailable"] += 1
            else:
                d = diag[0]
                ils["entered"] += d["ils_entered"]
                ils["iterations_attempted"] += d["ils_iterations_attempted"]
                ils["iterations_completed"] += d["ils_iterations_completed"]
                ils["runs_with_completed_iteration"] += d["ils_iterations_completed"] > 0
                ils["runs_with_new_global_best"] += d["ils_found_new_global_best"]
                ils["global_best_updates"] += d["ils_global_best_updates"]
                ils["budget_exhausted_before_ils"] += d["budget_exhausted_before_ils"]
                ils["budget_exhausted_during_ils"] += d["budget_exhausted_during_ils"]
            if vnd:
                costs.append({"case_id": case["case_id"], "vnd_status": vnd["status"], "ils_status": extended["status"],
                    "additional_seconds": extended["runtime_seconds"]-vnd["runtime_seconds"],
                    "additional_work": extended["operations_used"]-vnd["operations_used"],
                    "note": "resource accounting for all attempted cases, not a completed-quality comparison"})
    summary = summarize(bundle["cases"])
    return {"split": bundle["split"], "instances": len(seen), "method_records_verified": records,
            "protocol_fingerprint": bundle["protocol"]["protocol_fingerprint"],
            "summary": summary, "ils": ils, "construction_vnd_attribution": attribution,
            "ils_additional_resources": costs}


def write_audit(bundle, output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    audit = audit_bundle(bundle)
    (output / "audit.json").write_text(json.dumps(audit, indent=2, allow_nan=False), encoding="utf-8")
    for name in ("construction_vnd_attribution", "ils_additional_resources"):
        rows = audit[name]
        if rows:
            with (output / (name + ".csv")).open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
                writer.writeheader(); writer.writerows(rows)
    lines = [f"# Methodology audit: {bundle['split']}", "",
        f"Verified {audit['instances']} instances and {audit['method_records_verified']} method records.",
        f"Frozen protocol: `{audit['protocol_fingerprint']}`.", "",
        "All objectives, driver counts, constraints, matrices and units are checked through the full problem fingerprint. Routes and costs are independently recomputed without calling the canonical validator.",
        "Primary paired results require both methods to be completed, feasible and nonfailed. Incomplete results are preserved, not promoted. Zero eligible pairs means no estimate.", "",
        "## ILS execution evidence", "", "```json", json.dumps(audit["ils"], indent=2), "```", "",
        "An ILS attempt counter is not a completed iteration: only the existing ils_acceptance event closes an iteration. Global-best gains are measured after the first perturbation. Budget limits keep the solver's original incomplete status, including the configured ILS iteration limit.",
        "Additional runtime/work CSV accounts for all attempts with explicit statuses; it is not evidence of solution-quality superiority. No inference of benefit is made from incomplete pairs.", "",
        "## Construction and assignment", "",
        "The attribution CSV decomposes historical NN+2-Opt -> best construction -> final VND distance on each identical problem. It marks completed-pair eligibility. This is trajectory accounting, not a causal ablation: constructors change assignment and ordering together, while operators have order-dependent effects. Historical round-robin assignment is unchanged. Larger work consumption is visible alongside costs.", "",
        "## Completed paired comparisons", "", "| Method | Reference | Eligible | Excluded | Mean % | Median % | W/T/L |", "|---|---|---:|---:|---:|---:|---|"]
    for row in audit["summary"]["paired"]:
        s = row["improvement_percent"]
        lines.append(f"|{row['method']}|{row['baseline']}|{row['valid_pairs']}|{row['unavailable_pairs']}|{s['mean']}|{s['median']}|{row['wins']}/{row['ties']}/{row['losses']}|")
    lines += ["", "Confidence intervals, dispersion, all exclusion denominators, runtime/work distributions and per-instance evidence are in JSON and the split report. Best observed is not a proven optimum; completion conditioning and concurrent CPU contention limit interpretation."]
    (output / "audit.md").write_text("\n".join(lines), encoding="utf-8")
    return audit


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--rewrite-report", action="store_true", help="Write strict-pairing report to a NEW subdirectory")
    args = parser.parse_args(argv)
    bundle = json.loads(Path(args.results).read_text(encoding="utf-8"))
    result = write_audit(bundle, args.output)
    if args.rewrite_report:
        write_reports(bundle, Path(args.output) / "completed-only-report")
    print(f"Audited {result['instances']} cases; {result['method_records_verified']} records; split={result['split']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
