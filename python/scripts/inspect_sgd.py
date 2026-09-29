"""Inspect public SGD structure without importing any dialogue for training."""
import argparse
from collections import Counter
import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[2]
for path in (REPO_ROOT / "python/src", REPO_ROOT / "python", REPO_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from dusnx_core.data_pipeline import redact,sha256

if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("--directory",default="runtime/external-data/sgd")
    directory=Path(parser.parse_args().directory)
    dialogues=json.loads((directory/"dialogues_001.json").read_text(encoding="utf-8"))
    schema=json.loads((directory/"schema.json").read_text(encoding="utf-8"))
    turns=[turn for d in dialogues for turn in d["turns"]]
    report=dict(reference_only=True,dialogues=len(dialogues),turns=len(turns),services_in_schema=len(schema),
        dialogue_fields=sorted(dialogues[0]),turn_fields=sorted(turns[0]),
        speakers=dict(Counter(t["speaker"] for t in turns)),
        samples=[dict(speaker=t["speaker"],utterance=redact(t["utterance"]),
                      frame_fields=[sorted(f) for f in t["frames"]]) for t in turns[:3]],
        sha256={p.name:sha256(p) for p in (directory/"schema.json",directory/"dialogues_001.json")})
    (directory/"inspection.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(report,ensure_ascii=False,indent=2))
