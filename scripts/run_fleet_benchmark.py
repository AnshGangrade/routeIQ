"""Offline fleet benchmarks. Explicit frozen protocol required for held-out runs."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine.evaluation.fleet_benchmark import BenchmarkConfig, protocol, run_case, verify_protocol
from engine.evaluation.fleet_dataset import SPLITS, case_by_id, cases
from engine.evaluation.fleet_reporting import write_reports


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--split", choices=SPLITS, default="development")
    parser.add_argument("--profile", choices=("smoke", "full"), default="smoke")
    parser.add_argument("--case", help="Rerun exactly this versioned case ID (must match --split)")
    parser.add_argument("--operations", type=int)
    parser.add_argument("--seconds", type=float)
    parser.add_argument("--search-seed", type=int)
    parser.add_argument("--random-trials", type=int)
    parser.add_argument("--workers", type=int, help="Frozen maximum case concurrency for the full campaign")
    parser.add_argument("--output", default="runs/fleet-benchmark")
    parser.add_argument("--freeze-protocol", help="Write an exclusive protocol file and exit without evaluating")
    parser.add_argument("--protocol", help="Use an existing frozen protocol without parameter overrides")
    parser.add_argument("--acknowledge-heldout", action="store_true",
                        help="Final evaluation only; do not tune against its results")
    args = parser.parse_args(argv)
    try:
        if args.freeze_protocol and args.protocol:
            raise ValueError("Choose freeze or load, not both")
        if args.split == "heldout" and (not args.protocol or not args.acknowledge_heldout):
            raise ValueError("Held-out requires --protocol and --acknowledge-heldout")
        overrides = {k: getattr(args, k) for k in ("operations", "seconds", "search_seed", "random_trials", "workers")
                     if getattr(args, k) is not None}
        if args.protocol:
            if overrides:
                raise ValueError("Frozen protocols cannot be overridden")
            saved = json.loads(Path(args.protocol).read_text(encoding="utf-8"))
            config = verify_protocol(saved, ROOT)
        else:
            config = BenchmarkConfig(**overrides)
            saved = protocol(config, ROOT)
        if args.freeze_protocol:
            path = Path(args.freeze_protocol)
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("x", encoding="utf-8") as stream:
                json.dump(saved, stream, indent=2, allow_nan=False)
            print(f"Frozen protocol: {path}")
            return 0
        selected = (case_by_id(args.case),) if args.case else cases(args.split, args.profile)
        if any(case.split != args.split for case in selected):
            raise ValueError("Case does not belong to requested split")
        output = Path(args.output)
        if output.exists():
            raise ValueError("Output already exists; choose a new directory")
        measured = []
        for index, case in enumerate(selected, 1):
            result = run_case(case, config)
            measured.append(result)
            statuses = ", ".join(f"{r['method']}={r['status']}" for r in result["results"])
            print(f"{index}/{len(selected)} {case.id}: {statuses}", flush=True)
        bundle = {"schema": "fleet-benchmark-results/v1", "split": args.split,
                  "profile": "single_case" if args.case else args.profile, "protocol": saved,
                  "recorded_at_utc": datetime.now(timezone.utc).isoformat(), "cases": measured}
        write_reports(bundle, output)
        print(f"Reports: {output} ({len(measured)} cases)")
        return int(any(row["evaluation_failure"] for case in measured for row in case["results"]))
    except (ValueError, OSError, KeyError, TypeError) as exc:
        # These are local CLI/config errors, not provider exception bodies.
        parser.error(str(exc))


if __name__ == "__main__":
    raise SystemExit(main())
