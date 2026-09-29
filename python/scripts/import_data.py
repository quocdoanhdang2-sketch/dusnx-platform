"""Inspect safe samples before import. No guessed labels or chained single turns."""
import argparse
import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[2]
for path in (REPO_ROOT / "python/src", REPO_ROOT / "python", REPO_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from dusnx_core.data_pipeline import inspect_source,import_source,write_rows


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input",required=True);p.add_argument("--source",choices=["massive","csconda"],required=True)
    p.add_argument("--output-dir",default="runtime/imported");p.add_argument("--inspect-only",action="store_true")
    p.add_argument("--mapping",default="configs/massive_vi_mapping.json");p.add_argument("--text-field")
    a=p.parse_args();out=Path(a.output_dir);out.mkdir(parents=True,exist_ok=True)
    rows,report=inspect_source(a.input,a.source,text_field=a.text_field)
    (out/"inspection.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(report,ensure_ascii=False,indent=2))
    if a.inspect_only:return
    cfg=json.loads(Path("configs/data_sources.json").read_text(encoding="utf-8"))[a.source]
    mapping=json.loads(Path(a.mapping).read_text(encoding="utf-8")) if a.source=="massive" else None
    if mapping and mapping["source_revision"]!=cfg["revision"]:raise ValueError("mapping revision mismatch")
    accepted,report=import_source(rows,a.source,cfg["revision"],mapping,text_field=a.text_field)
    write_rows(out/"candidates.jsonl",accepted)
    (out/"report.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({k:v for k,v in report.items() if k!='stats'},ensure_ascii=False))


if __name__=="__main__":main()
