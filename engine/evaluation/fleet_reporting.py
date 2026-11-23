"""Completed-only paired quality and separately reported completion/cost measurements."""
import csv
import io
import json
import math
import random
import statistics
from pathlib import Path

REL_TOL = 1e-9
ABS_TOL = 1e-9


def tied(a, b):
    # Exact zero has a defined special percentage rule. A positive cost must not
    # be simultaneously an undefined zero-reference loss and a tolerance tie.
    if a == 0 or b == 0:
        return a == b
    return math.isclose(a, b, rel_tol=REL_TOL, abs_tol=ABS_TOL)


def improvement(reference, candidate):
    """Positive is shorter. A positive cost against exact zero has no finite %.

    Tolerance affects W/T/L only; percentages retain the measured differences.
    """
    if reference == 0:
        return 0. if candidate == 0 else None
    return 100. * (reference - candidate) / reference


def usable(row):
    return row["feasible"] and not row["evaluation_failure"]


def _statistics(values):
    if not values:
        return {"n": 0, "mean": None, "median": None, "sample_sd": None, "mean_ci95": None,
                "minimum": None, "maximum": None, "p95": None}
    ci = None
    if len(values) >= 2:
        rng = random.Random(0)
        means = sorted(math.fsum(rng.choices(values, k=len(values)))/len(values) for _ in range(1000))
        ci = [means[24], means[974]]
    return {"n": len(values), "mean": statistics.mean(values), "median": statistics.median(values),
            "minimum": min(values), "maximum": max(values), "p95": sorted(values)[math.ceil(.95*len(values))-1],
            "sample_sd": statistics.stdev(values) if len(values) >= 2 else None, "mean_ci95": ci}


def summarize(cases):
    methods = list(dict.fromkeys(row["method"] for case in cases for row in case["results"]))
    summary = {"instances": len(cases), "methods": {}, "paired": []}
    for case in cases:
        valid = [row["total_distance"] for row in case["results"] if usable(row)]
        best = min(valid) if valid else None
        case["best_observed_distance"] = best
        for row in case["results"]:
            # Include validated incomplete incumbents, but never failed evaluations.
            value = row["total_distance"]
            row["gap_to_best_observed_percent"] = (None if best is None or not usable(row)
                else (0. if value == 0 else None) if best == 0 else 100. * (value-best)/best)
    for method in methods:
        rows = [row for case in cases for row in case["results"] if row["method"] == method]
        applicable = [row for row in rows if row["status"] != "not_applicable"]
        denominator = len(applicable)
        def rate(key):
            return sum(bool(row[key]) for row in applicable) / denominator if denominator else None
        summary["methods"][method] = {
            "attempted": denominator, "not_applicable": len(rows)-denominator,
            "completed": sum(row["status"] == "completed" for row in rows),
            "incomplete": sum(row["status"] == "incomplete" for row in rows),
            "failed": sum(row["status"] == "failed" for row in rows),
            "feasible_results": sum(row["feasible"] for row in applicable),
            "no_feasible_result_rate": (sum(not row["feasible"] for row in applicable) / denominator
                                         if denominator else None),
            "feasibility_failure_rate": (sum(row["termination_reason"] == "invalid_solution" for row in applicable)
                                         / denominator if denominator else None),
            "evaluation_failure_rate": rate("evaluation_failure"),
            "timeout_rate": rate("timeout"), "budget_exhaustion_rate": rate("budget_exhausted"),
            "runtime_seconds": _statistics([row["runtime_seconds"] for row in applicable]),
            "work_distribution": _statistics([row["operations_used"] for row in applicable]),
            "operator_calls_distribution": _statistics([row["operator_calls"] for row in applicable]),
            "operations_used": sum(row["operations_used"] for row in rows),
            "operator_calls": sum(row["operator_calls"] for row in rows),
            "accepted_moves_reported": sum(row["accepted_moves"] or 0 for row in rows),
            "accepted_moves_unavailable_runs": sum(row["accepted_moves"] is None for row in rows)}
    for method in methods:
        for baseline in methods:
            if method == baseline:
                continue
            values, complete_values, wins, ties, losses, pairs, incomplete = [], [], 0, 0, 0, 0, 0
            undefined, worst, regressions, zero_reference_losses = 0, None, 0, 0
            worst_absolute, worst_absolute_case = 0., None
            worst_case = None
            excluded = {"missing": 0, "failed": 0, "inapplicable": 0, "incomplete": 0, "no_feasible_result": 0}
            for case in cases:
                by_name = {r["method"]: r for r in case["results"]}
                a, b = by_name.get(method), by_name.get(baseline)
                if not a or not b:
                    excluded["missing"] += 1
                    continue
                if a["evaluation_failure"] or b["evaluation_failure"] or "failed" in (a["status"], b["status"]):
                    excluded["failed"] += 1
                    continue
                if "not_applicable" in (a["status"], b["status"]):
                    excluded["inapplicable"] += 1
                    continue
                if a["status"] != "completed" or b["status"] != "completed":
                    excluded["incomplete"] += 1
                    continue
                if not usable(a) or not usable(b):
                    excluded["no_feasible_result"] += 1
                    continue
                pairs += 1
                partial = a["status"] != "completed" or b["status"] != "completed"
                incomplete += partial
                x, y = a["total_distance"], b["total_distance"]
                if tied(x, y):
                    ties += 1
                elif x < y:
                    wins += 1
                else:
                    losses += 1
                delta = x-y
                if delta > 0:
                    regressions += 1
                if delta > worst_absolute:
                    worst_absolute, worst_absolute_case = delta, case["case_id"]
                percent = improvement(y, x)
                if percent is None:
                    undefined += 1
                    zero_reference_losses += 1
                else:
                    values.append(percent)
                    if not partial:
                        complete_values.append(percent)
                    if worst is None or percent < worst:
                        worst, worst_case = percent, case["case_id"]
            summary["paired"].append({"method": method, "baseline": baseline,
                "instances": len(cases), "valid_pairs": pairs, "unavailable_pairs": len(cases)-pairs,
                "eligibility": "both_completed_feasible_nonfailed", "excluded_pairs": excluded,
                "incomplete_pairs": incomplete, "complete_pairs": pairs-incomplete,
                "wins": wins, "ties": ties, "losses": losses, "undefined_percentage_pairs": undefined,
                "percentage_pairs": len(values), "improvement_percent": _statistics(values),
                "complete_pairs_improvement_percent": _statistics(complete_values),
                "worst_regression_percent": (max(0., -worst) if worst is not None
                                               and not zero_reference_losses else None),
                "worst_finite_regression_percent": max(0., -worst) if worst is not None else None,
                "zero_reference_losses": zero_reference_losses,
                "worst_absolute_regression": worst_absolute,
                "worst_absolute_regression_case": worst_absolute_case,
                "worst_defined_pair_improvement_percent": worst, "worst_defined_pair_case": worst_case,
                "raw_regression_pairs": regressions})
    return summary


def _fmt(value):
    return "n/a" if value is None else f"{value:.4f}"


def markdown(bundle):
    summary = bundle["summary"]
    lines = ["# RouteIQ fleet benchmark", "", f"Split: **{bundle['split']}**. Profile: **{bundle['profile']}**.",
             f"Instances measured: **{summary['instances']}**. Protocol: `{bundle['protocol']['protocol_fingerprint']}`.",
             "", "Best observed means the shortest independently validated, nonfailed incumbent in this run; it is not a proven optimum.",
             "Incomplete feasible incumbents remain in per-instance results and best-observed gaps, but are excluded from paired comparisons. Both methods must be completed, feasible and nonfailed. Missing, failed, inapplicable and incomplete pairs have explicit denominators in JSON.",
             "", "## Method completion and cost", "",
             "| Method | Attempted | Complete | Incomplete | Failed | Inapplicable | Mean seconds | Work | Timeout rate | Budget rate | No feasible result rate | Evaluation failure rate |",
             "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for name, row in summary["methods"].items():
        lines.append(f"| {name} | {row['attempted']} | {row['completed']} | {row['incomplete']} | {row['failed']} | {row['not_applicable']} | {_fmt(row['runtime_seconds']['mean'])} | {row['operations_used']} | {_fmt(row['timeout_rate'])} | {_fmt(row['budget_exhaustion_rate'])} | {_fmt(row['no_feasible_result_rate'])} | {_fmt(row['evaluation_failure_rate'])} |")
    lines += ["", "## Paired quality (positive percentage means shorter)", "",
              "Tolerance for W/T/L: abs=1e-9, rel=1e-9. Exact zero reference: 0 vs 0 is 0%; positive vs 0 is undefined and remains a loss.",
              "Mean 95% intervals use 1,000 fixed-seed instance bootstrap resamples; descriptive, not multiple-comparison significance tests. Smoke coverage is not balanced and does not justify population claims.",
              "Means/medians divide by percentage_pairs: eligible completed pairs with a defined percentage. W/T/L uses all eligible completed pairs, including undefined zero-reference percentages. Completion conditioning may favor easier cases; inspect excluded counts.",
              "", "| Method vs baseline | Completed pairs / unavailable | Excluded incomplete | W / T / L | Mean % | Median % | SD | Mean 95% CI | Worst regression % | Undefined % pairs |",
              "|---|---:|---:|---:|---:|---:|---:|---|---:|---:|"]
    for row in summary["paired"]:
        s = row["improvement_percent"]
        lines.append(f"| {row['method']} vs {row['baseline']} | {row['valid_pairs']} / {row['unavailable_pairs']} | {row['excluded_pairs']['incomplete']} | {row['wins']} / {row['ties']} / {row['losses']} | {_fmt(s['mean'])} | {_fmt(s['median'])} | {_fmt(s['sample_sd'])} | {s['mean_ci95']} | {_fmt(row['worst_regression_percent'])} | {row['undefined_percentage_pairs']} |")
    lines += ["", "## Per-instance results", "",
              "All distances use each case's recorded units. JSON includes full FleetProblem snapshots, routes, construction statuses, work categories, and complete-only paired summaries.",
              "", "| Case | Method | Status / reason | Total | Longest | Gap % | Seconds | Operations | Calls | Accepted |",
              "|---|---|---|---:|---:|---:|---:|---:|---:|---:|"]
    for case in bundle["cases"]:
        for row in case["results"]:
            lines.append(f"| {case['case_id']} | {row['method']} | {row['status']} / {row['termination_reason']} | {_fmt(row['total_distance'])} | {_fmt(row['longest_route_distance'])} | {_fmt(row['gap_to_best_observed_percent'])} | {_fmt(row['runtime_seconds'])} | {row['operations_used']} | {row['operator_calls']} | {row['accepted_moves']} |")
    lines += ["", "## Reproduction", "", "Configuration and software versions:", "", "```json",
              json.dumps(bundle["protocol"], indent=2), "```", "",
              "Budgets are cooperative, not hard process timeouts. Work units count heterogeneous candidate checks/calls, not equal CPU instructions. Historical 2-Opt accepted reversal counts are unavailable (null). Hybrid accepted moves count VND proposals; internal 2-Opt reversals are not exposed.",
              "The portfolio includes the solver's ordered feasible fallback. No global-optimality or universal-improvement claim is made.", ""]
    return "\n".join(lines)


def write_reports(bundle, directory):
    directory = Path(directory)
    # Refuse overwriting prior experiments, especially held-out records.
    directory.mkdir(parents=True, exist_ok=False)
    bundle["summary"] = summarize(bundle["cases"])
    (directory / "results.json").write_text(json.dumps(bundle, indent=2, allow_nan=False), encoding="utf-8")
    (directory / "report.md").write_text(markdown(bundle), encoding="utf-8")
    rows = [{"case_id": case["case_id"], **case["case"], **row} for case in bundle["cases"] for row in case["results"]]
    if rows:
        fields = list(dict.fromkeys(key for row in rows for key in row))
        stream = io.StringIO(newline="")
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows({k: json.dumps(v, allow_nan=False) if isinstance(v, (dict, list, tuple)) else v
                          for k, v in row.items()} for row in rows)
        (directory / "results.csv").write_text(stream.getvalue(), encoding="utf-8")
