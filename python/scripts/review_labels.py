import argparse
import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[2]
for path in (REPO_ROOT / "python/src", REPO_ROOT / "python", REPO_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from dusnx_core.data_pipeline import read_rows,write_rows
from dusnx_core.review import review_sample,agreement

if __name__=="__main__":
    ap=argparse.ArgumentParser();ap.add_argument("--input",required=True);ap.add_argument("--output",required=True)
    ap.add_argument("--compare");ap.add_argument("--sequences",type=int,default=10);ap.add_argument("--seed",type=int,default=42)
    a=ap.parse_args()
    if a.compare:Path(a.output).write_text(json.dumps(agreement(read_rows(a.input),read_rows(a.compare)),ensure_ascii=False,indent=2),encoding="utf-8")
    else:write_rows(a.output,review_sample(read_rows(a.input),a.seed,a.sequences))
