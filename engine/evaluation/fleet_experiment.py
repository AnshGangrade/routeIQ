"""Durable per-case checkpoints and strict split aggregation for long experiments."""
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime, timezone
import json
from pathlib import Path

from engine.routing import FleetProblem, validate_fleet_solution
from .fleet_benchmark import run_case
from .fleet_dataset import cases, digest
from .fleet_reporting import summarize, write_reports


def save_json_exclusive(path, value):
    # A torn checkpoint is never accepted: hash and schema checks fail on resume.
    with Path(path).open("x", encoding="utf-8") as stream:
        json.dump(value, stream, allow_nan=False, separators=(",", ":"))


def load_case(path, case, config, protocol_hash):
    envelope = json.loads(Path(path).read_text(encoding="utf-8"))
    result = envelope["result"]
    if envelope["protocol_fingerprint"] != protocol_hash or envelope["checksum"] != digest(result):
        raise ValueError("Checkpoint protocol or checksum mismatch")
    expected = case.problem(config.search_seed)
    actual = FleetProblem.model_validate(result["problem"])
    if (result["case_id"] != case.id or actual != expected
            or result["problem_fingerprint"] != expected.fingerprint
            or result["matrix_fingerprint"] != expected.matrix_fingerprint):
        raise ValueError("Checkpoint case or problem mismatch")
    if [row["method"] for row in result["results"]] != list(config.methods):
        raise ValueError("Checkpoint method coverage mismatch")
    for row in result["results"]:
        if (row["problem_fingerprint"] != expected.fingerprint
                or row["matrix_fingerprint"] != expected.matrix_fingerprint
                or row["search_seed"] != config.search_seed
                or row["operation_limit"] != config.operations
                or row["time_limit_seconds"] != config.seconds):
            raise ValueError("Checkpoint method input or budget mismatch")
        if row["feasible"]:
            checked = validate_fleet_solution(actual, row["routes"])
            if (checked.total_distance != row["total_distance"]
                    or checked.longest_route_distance != row["longest_route_distance"]):
                raise ValueError("Checkpoint cost mismatch")
    return result


def run_split(split, config, saved_protocol, directory, *, resume=False):
    """Fixed catalog order, independent case processes, sequential methods per case.

    workers is an execution setting in the frozen configuration, not a solver
    budget multiplier. Every method retains its unchanged per-case limits.
    """
    directory = Path(directory)
    selected = cases(split, "full")
    manifest = {"schema": "fleet-experiment/v1", "split": split,
                "protocol": saved_protocol, "case_ids": [case.id for case in selected],
                "maximum_concurrent_cases": config.workers,
                "method_order": list(config.methods)}
    if resume:
        if json.loads((directory / "manifest.json").read_text(encoding="utf-8")) != manifest:
            raise ValueError("Resume manifest does not match frozen experiment")
    else:
        directory.mkdir(parents=True, exist_ok=False)
        (directory / "cases").mkdir()
        save_json_exclusive(directory / "manifest.json", manifest)
    results, pending = {}, []
    for case in selected:
        path = directory / "cases" / (case.id + ".json")
        if path.exists():
            results[case.id] = load_case(path, case, config, saved_protocol["protocol_fingerprint"])
        else:
            pending.append(case)
    print(f"{split}: {len(results)}/{len(selected)} verified checkpoints; {len(pending)} pending", flush=True)
    # No validation/test outcomes are used to select parameters or future cases.
    with ProcessPoolExecutor(max_workers=config.workers) as pool:
        tasks = {pool.submit(run_case, case, config): case for case in pending}
        for future in as_completed(tasks):
            case = tasks[future]
            # Infrastructure failures stop the campaign; absent checkpoints remain
            # explicitly pending. Never convert a crashed worker into a good score.
            result = future.result()
            save_json_exclusive(directory / "cases" / (case.id + ".json"),
                {"protocol_fingerprint": saved_protocol["protocol_fingerprint"],
                 "checksum": digest(result), "result": result})
            results[case.id] = result
            print(f"{split}: {len(results)}/{len(selected)} {case.id} " +
                  ",".join(f"{r['method']}={r['status']}" for r in result["results"]), flush=True)
    bundle = {"schema": "fleet-benchmark-results/v2", "split": split, "profile": "full",
              "protocol": saved_protocol, "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
              "execution": manifest, "cases": [results[case.id] for case in selected]}
    report_path = directory / "report"
    if not report_path.exists():
        write_reports(bundle, report_path)
    else:
        # Resume cannot silently accept a partial/foreign report as a full suite.
        old = json.loads((report_path / "results.json").read_text(encoding="utf-8"))
        checked_summary = summarize(bundle["cases"])
        if (old["protocol"] != saved_protocol or digest(old["cases"]) != digest(bundle["cases"])
                or old["summary"] != checked_summary
                or not all((report_path / name).is_file() for name in ("results.csv", "report.md"))):
            raise ValueError("Existing report is not this complete experiment")
    return bundle
