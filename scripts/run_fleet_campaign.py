"""Run complete development, validation and held-out splits without retuning."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine.evaluation.fleet_benchmark import verify_protocol
from engine.evaluation.fleet_experiment import run_split, save_json_exclusive
from engine.evaluation.fleet_dataset import SPLITS


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--acknowledge-heldout", action="store_true")
    args = parser.parse_args(argv)
    if not args.acknowledge_heldout:
        parser.error("The campaign includes held-out: --acknowledge-heldout is required")
    try:
        saved = json.loads(Path(args.protocol).read_text(encoding="utf-8"))
        config = verify_protocol(saved, ROOT)
        output = Path(args.output)
        manifest = {"protocol": saved, "split_order": list(SPLITS),
                    "tuning": "none; configuration frozen before all three splits"}
        if args.resume:
            if json.loads((output / "campaign.json").read_text(encoding="utf-8")) != manifest:
                raise ValueError("Campaign resume protocol mismatch")
        else:
            output.mkdir(parents=True, exist_ok=False)
            save_json_exclusive(output / "campaign.json", manifest)
        failures = 0
        for split in SPLITS:
            # Verify source/config again before each split, including held-out.
            verify_protocol(saved, ROOT)
            path = output / split
            bundle = run_split(split, config, saved, path, resume=args.resume and path.exists())
            failures += sum(r["evaluation_failure"] for c in bundle["cases"] for r in c["results"])
            print(f"SPLIT FINISHED: {split}; {len(bundle['cases'])} cases", flush=True)
        print(f"CAMPAIGN FINISHED: 1080 cases; evaluation failures={failures}", flush=True)
        return int(bool(failures))
    except (ValueError, OSError, KeyError, TypeError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    raise SystemExit(main())
