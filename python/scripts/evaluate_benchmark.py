from __future__ import annotations

import argparse
import json

import torch

from dusnx_core.benchmark import evaluate_benchmark, read_benchmark, write_report
from dusnx_core.checkpoint import load_checkpoint, model_identifier
from dusnx_core.inference import process_one


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate a labelled benchmark_v1 JSONL file.")
    parser.add_argument("--benchmark", required=True)
    parser.add_argument("--checkpoint", default="artifacts/dusnx_smoke_v2.pt")
    parser.add_argument("--output-dir", default="runtime/benchmark-report")
    parser.add_argument("--device", choices=["cpu", "cuda", "auto"], default="auto")
    args = parser.parse_args()

    device = "cuda" if args.device != "cpu" and torch.cuda.is_available() else "cpu"
    model, cfg, _ = load_checkpoint(args.checkpoint, device)
    model_version = model_identifier(args.checkpoint, cfg, "trained_dusnx")
    steps = read_benchmark(args.benchmark)

    def infer(request):
        return process_one(model, cfg, request, model_version, device)

    report = evaluate_benchmark(
        steps,
        infer,
        checkpoint=args.checkpoint,
        model_version=model_version,
    )
    write_report(report, args.output_dir)
    print(json.dumps({
        "report": f"{args.output_dir}/report.json",
        "case_count": report["case_count"],
        "sequence_count": report["sequence_count"],
        "model_intent_macro_f1_all_classes": (
            report["metrics"]["model"]["intent"]["macro_f1_all_classes"]
        ),
        "after_rule_override_intent_macro_f1_all_classes": (
            report["metrics"]["after_rule_override"]["intent"]["macro_f1_all_classes"]
        ),
    }, indent=2))


if __name__ == "__main__":
    main()
