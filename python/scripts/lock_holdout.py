"""Create v1 once, before training/evaluation. Refuses to replace locked labels."""
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[2]
for path in (REPO_ROOT / "python/src", REPO_ROOT / "python", REPO_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from dusnx_core.data_pipeline import write_rows,lock_holdout,assert_disjoint,read_rows
from dusnx_core.designed_data import make_holdout

if __name__=="__main__":
    path=Path("benchmarks/holdout_v1.jsonl");manifest=path.with_suffix(".manifest.json")
    if path.exists() or manifest.exists():raise SystemExit("Already exists; never regenerate locked labels")
    rows=make_holdout()
    excluded=[Path("runtime/prepared/train.jsonl"),Path("runtime/prepared/validation.jsonl")]
    assert_disjoint({"holdout":rows,**{p.stem:read_rows(p) for p in excluded}})
    write_rows(path,rows)
    print(lock_holdout(path,manifest,seed=914207,excluded_paths=[*excluded,Path("benchmarks/week3_personalization_pilot.jsonl")]))
