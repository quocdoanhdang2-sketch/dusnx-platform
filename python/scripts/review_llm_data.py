"""Export and apply human-readable SFT review packages."""
import argparse
import json
from dusnx_core.llm_review import apply_package, export_package


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    export = sub.add_parser("export")
    export.add_argument("--data", default="datasets/llm_sft")
    export.add_argument("--output", required=True)
    export.add_argument("--kind", choices=("train-validation", "test"), required=True)
    export.add_argument("--human-author")
    export.add_argument("--human-authored-at")
    apply = sub.add_parser("apply")
    apply.add_argument("--data", default="datasets/llm_sft")
    apply.add_argument("--package", required=True)
    apply.add_argument("--reviewed-csv")
    args = parser.parse_args()
    if args.command == "export":
        splits = ("train", "validation") if args.kind == "train-validation" else ("test",)
        count = export_package(args.data, args.output, splits, args.human_author, args.human_authored_at)
        print(json.dumps({"status": "exported", "rows": count, "output": args.output}, ensure_ascii=False))
    else:
        receipt = apply_package(args.data, args.package, args.reviewed_csv)
        print(json.dumps({"status": "applied", "receipt": receipt}, ensure_ascii=False))


if __name__ == "__main__":
    main()
