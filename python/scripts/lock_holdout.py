"""Create and lock holdout benchmark once, before training/evaluation. Refuses to replace locked labels."""
import argparse
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[2]
for path in (REPO_ROOT / "python/src", REPO_ROOT / "python", REPO_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from dusnx_core.data_pipeline import write_rows, lock_holdout, assert_disjoint, read_rows
from dusnx_core.designed_data import make_holdout, make_holdout_v2

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Lock holdout benchmark")
    parser.add_argument("--version", choices=["v1", "v2"], default="v2", help="Holdout version to lock")
    parser.add_argument("--output", help="Optional explicit output path")
    args = parser.parse_args()

    if args.version == "v1":
        path = Path(args.output) if args.output else Path("benchmarks/holdout_v1.jsonl")
        seed = 914207
        generator = make_holdout
    else:
        path = Path(args.output) if args.output else Path("benchmarks/holdout_v2.jsonl")
        seed = 20261001
        generator = make_holdout_v2

    manifest = path.with_suffix(".manifest.json")
    if path.exists() or manifest.exists():
        raise SystemExit(f"{path} or {manifest} already exists; never regenerate locked labels")

    rows = generator(seed=seed)
    excluded = [
        p for p in (
            Path("runtime/prepared/train.jsonl"),
            Path("runtime/prepared/validation.jsonl"),
            Path("benchmarks/week3_personalization_pilot.jsonl"),
            Path("benchmarks/holdout_v1.jsonl") if args.version != "v1" else None,
        ) if p and p.exists()
    ]
    check_partitions = {"holdout": rows}
    for p in excluded:
        if p.name.endswith(".jsonl"):
            # Normalize sequence fields for benchmark disjoint check
            check_partitions[p.stem] = [
                dict(
                    global_user_id=r.get("global_user_id") or "bench-" + r["sequence_id"],
                    sequence_id=r["sequence_id"],
                    template_family=r.get("template_family") or "bench-" + r["sequence_id"],
                    user_message=r.get("user_message", r.get("content", "")),
                )
                for r in read_rows(p)
            ]
    assert_disjoint(check_partitions)
    write_rows(path, rows)
    print(lock_holdout(path, manifest, seed=seed, excluded_paths=excluded))
