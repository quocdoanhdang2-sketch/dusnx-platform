"""Replay the existing pilot. TestClient measures app behavior, not Web/Gateway.

All arms use the same LLM and per-session history. Static memory is append-only:
prior explicit remember/change messages remain, without confirmation/superseding.
Inputs are allowlisted before replay. Labels are used only after prediction.
"""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import secrets
import sys
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[2]
for path in (REPO_ROOT / "python/src", REPO_ROOT / "python", REPO_ROOT):
    sys.path.insert(0, str(path))
from dusnx_core.personalization_benchmark import read_pilot

SYSTEMS = ("baseline_a", "baseline_b", "dusnx")
RULE_SOURCES = {"explicit_memory", "decision_flow", "context_guard", "business_rule_override",
                "bootstrap_rules", "baseline_rule"}


def _hits(text, phrases):
    import unicodedata
    norm = lambda s: unicodedata.normalize("NFC", s or "").casefold()
    return [p for p in phrases if norm(p) in norm(text)]


def attribution(source):
    return "model" if source == "model" else "rule" if source in RULE_SOURCES else "unknown"


def score_turn(gold, pred):
    """Literal answer checks. IDs/retrieved text never count as answer recall.

    Null = inapplicable/unlabelled. Superseded mentions conservatively fail even
    when negated; human semantic review is still needed.
    """
    reply = pred.get("reply", "")
    ok = pred.get("provider_ok") is True and not pred.get("error")
    target, active, obsolete = gold["target_query"], gold["gold_active_facts"], gold["gold_obsolete_facts"]
    required, clarify = gold["expected_keywords"], gold["requires_clarification"]
    missing = [f for f in active if not _hits(reply, [f])]
    leaked, forbidden = _hits(reply, obsolete), _hits(reply, gold["forbidden_keywords"])
    asks = bool(_hits(reply, ["?", "vui lòng", "cho tôi biết", "nêu rõ", "cung cấp thêm", "xác nhận"]))
    clarification_ok = asks and bool(_hits(reply, required or ["chưa", "bối cảnh", "rõ", "quyết định"]))

    is_revision = gold.get("expected_next_action") == "update_memory" or gold.get("expected_intent") == "decision_update"
    revision_ok = None
    if is_revision and active:
        pred_active = pred.get("active_memories", [])
        revision_ok = all(any(_hits(m, [a]) for m in pred_active) for a in active)

    metrics = {
        "update_revision_accuracy": revision_ok,
        "active_recall": ok and not missing if target and active else None,
        "obsolete_elimination": ok and not leaked if target and obsolete else None,
        "missing_context_handling": ok and clarification_ok if clarify else None,
    }
    for metric, expected, predicted in (
        ("intent", "expected_intent", "predicted_intent"),
        ("agent", "expected_agent", "predicted_agent"),
        ("action", "expected_next_action", "predicted_next_action"),
    ):
        metrics[metric] = pred.get(predicted) == gold[expected] if gold[expected] is not None else None
    metrics["final_answer_success"] = (ok and not missing and not leaked and not forbidden
        and (clarification_ok if clarify else all(_hits(reply, [p]) for p in required))) if target else None
    diagnosis = []
    if not ok:
        diagnosis.append(pred.get("error") or "provider_failed")
    if target and missing:
        diagnosis.append(f"missing current facts: {missing}")
    if target and leaked:
        diagnosis.append(f"obsolete mentions: {leaked}")
    if forbidden:
        diagnosis.append(f"forbidden phrases: {forbidden}")
    if clarify and not clarification_ok:
        diagnosis.append("clarification not detected")
    for name in ("intent", "agent", "action"):
        if metrics[name] is False:
            diagnosis.append(f"wrong {name}")
    if metrics["final_answer_success"] is False and not diagnosis:
        diagnosis.append("required answer keywords absent")
    return metrics, diagnosis



def run_baseline(turns, generate, *, static_memory):
    from apps.ai_api.main import _detect_remember_intent, _detect_decision_modify_intent
    from dusnx_core.routing_policy import match_explicit_route
    store, histories, out = [], defaultdict(list), []
    for turn in turns:
        content = turn["user_message"]
        route = match_explicit_route(turn["platform"], content)
        intent, agent, action = ((route.intent, route.agent, route.next_action) if route
                                  else ("chat", "conversation", "reply"))
        history = histories[turn["session_id"]]
        try:
            text, ok, provider, model, tokens = generate(
                user_message=content, memories=[{"info_type": "observation", "content": s} for s in store],
                intent=intent, session_history=list(history), project_name=turn["project_id"])
            pred = dict(reply=text, provider_ok=ok, provider_used=provider, model_used=model,
                        tokens_generated=tokens, error=None if ok else "provider_failed")
        except Exception as exc:
            pred = dict(reply="", provider_ok=False, error=type(exc).__name__)
        pred.update(predicted_intent=intent, predicted_agent=agent, predicted_next_action=action,
                    routing_source="baseline_rule", decision_source="rule", memories_used=list(store),
                    model_prediction=None)
        history.append({"role": "user", "content": content})
        if pred["provider_ok"]:
            history.append({"role": "assistant", "content": pred["reply"]})
        if static_memory and (_detect_remember_intent(content) or _detect_decision_modify_intent(content)):
            store.append(content)
        out.append(pred)
    return out


def request_json(client, method, path, **kwargs):
    response = client.request(method, path, **kwargs)
    if response.status_code >= 400:
        raise RuntimeError(f"{method} {path}: HTTP {response.status_code}")
    return response.json()


def run_dusnx(turns, client, main_mod, *, no_state=False, model_only=False):
    from dusnx_core import inference
    credentials = {"username": f"pilot_{secrets.token_hex(8)}", "password": secrets.token_urlsafe(24)}
    request_json(client, "POST", "/v1/auth/register", json=credentials)
    token = request_json(client, "POST", "/v1/auth/login", json=credentials)["token"]
    headers = {"Authorization": f"Bearer {token}"}
    sessions, projects, out = {}, {}, []
    original, raw_predictions = inference.process_one, []

    def observe(*args, **kwargs):
        if no_state:
            args = list(args)
            args[2] = args[2].model_copy(update={"previous_state": None})
        raw = original(*args, **kwargs)
        raw_predictions.append({"intent": raw["intent"], "agent": raw["selected_agent"],
                                "action": raw["next_action"]})
        return raw

    try:
        for turn in turns:
            raw_predictions.clear()
            try:
                pid, sid = turn["project_id"], turn["session_id"]
                if pid and pid not in projects:
                    projects[pid] = request_json(client, "POST", "/v1/projects", headers=headers,
                                                json={"name": pid})["project_id"]
                if sid not in sessions:
                    sessions[sid] = request_json(client, "POST", "/v1/sessions", headers=headers,
                                                json={"title": "Pilot session"})["session_id"]
                with patch.object(inference, "process_one", observe):
                    if model_only:
                        with patch.object(main_mod, "memory_answer", lambda *a, **k: None):
                            if turn["platform"] == "web":
                                res = request_json(client, "POST", "/v1/chat", headers=headers, json={
                                    "session_id": sessions[sid], "message": turn["user_message"],
                                    "project_id": projects.get(pid), "feedback_value": turn["known_feedback_value"]})
                            else:
                                res = request_json(client, "POST", "/v1/me/events", headers=headers, json={
                                    "platform": turn["platform"], "content": turn["user_message"],
                                    "project_id": projects.get(pid), "event_type": turn["event_type"],
                                    "feedback_value": turn["known_feedback_value"]})
                                res.update(reply="", provider_ok=True, provider_used="none")
                    else:
                        if turn["platform"] == "web":
                            res = request_json(client, "POST", "/v1/chat", headers=headers, json={
                                "session_id": sessions[sid], "message": turn["user_message"],
                                "project_id": projects.get(pid), "feedback_value": turn["known_feedback_value"]})
                        else:
                            res = request_json(client, "POST", "/v1/me/events", headers=headers, json={
                                "platform": turn["platform"], "content": turn["user_message"],
                                "project_id": projects.get(pid), "event_type": turn["event_type"],
                                "feedback_value": turn["known_feedback_value"]})
                            res.update(reply="", provider_ok=True, provider_used="none")

                raw_model = raw_predictions[-1] if raw_predictions else None
                if model_only and raw_model:
                    pred_intent = raw_model["intent"]
                    pred_agent = raw_model["agent"]
                    pred_action = raw_model["action"]
                    source = "pure_checkpoint"
                    decision_src = "model"
                    ans_src = "provider_llm"
                else:
                    pred_intent = res.get("intent")
                    pred_agent = res.get("selected_agent")
                    pred_action = res.get("next_action")
                    source = res.get("routing_source", "unknown")
                    decision_src = attribution(source)
                    ans_src = res.get("answer_source", "application_rule")

                pred = dict(
                    reply=res.get("reply", ""),
                    provider_ok=res.get("provider_ok"),
                    provider_used=res.get("provider_used"),
                    model_used=res.get("model_used"),
                    tokens_generated=res.get("tokens_generated"),
                    routing_source=source,
                    decision_source=decision_src,
                    predicted_intent=pred_intent,
                    predicted_agent=pred_agent,
                    predicted_next_action=pred_action,
                    model_prediction=raw_model,
                    state_version=res.get("state_version"),
                    error=None,
                    answer_source=ans_src,
                    recurrent_state_disabled=no_state,
                    model_only_mode=model_only,
                )
                memories = request_json(client, "GET", "/v1/memories", headers=headers)
                used_ids = set(res.get("memory_ids_used", []))
                pred["memories_used"] = [m["content"] for m in memories if m["memory_id"] in used_ids]
                pred["active_memories"] = [m["content"] for m in memories if m["is_active"]]
            except Exception as exc:
                pred = dict(reply="", provider_ok=False, error=f"{type(exc).__name__}: {exc}",
                            decision_source="unknown", model_prediction=None)
            out.append(pred)
    finally:
        try:
            request_json(client, "POST", "/v1/auth/logout", headers=headers)
        except Exception as exc:
            # Keep completed predictions even if cleanup fails.
            if out:
                out[-1]["logout_error"] = type(exc).__name__
    return out



def wilson_ci(passed, scored, z=1.96):

    if not scored:
        return None
    import math
    center = (passed + (z**2) / 2) / (scored + z**2)
    half = (z / (scored + z**2)) * math.sqrt((passed * (scored - passed) / scored) + (z**2) / 4)
    return [round(max(0.0, center - half), 4), round(min(1.0, center + half), 4)]


def aggregate(records):
    from dusnx_core.constants import INTENTS
    result = {}
    for system in dict.fromkeys(r["system"] for r in records):
        selected = [r for r in records if r["system"] == system]
        metrics = {}
        for key in ("update_revision_accuracy", "active_recall", "obsolete_elimination", "missing_context_handling",
                    "intent", "agent", "action", "final_answer_success"):
            values = [r["metrics"][key] for r in selected if r["metrics"][key] is not None]
            passed = sum(values)
            scored = len(values)
            metrics[key] = {
                "passed": passed,
                "scored": scored,
                "rate": passed / scored if scored else None,
                "ci_95": wilson_ci(passed, scored) if scored else None,
            }
        result[system] = {"metrics": metrics,
                          "attribution": dict(Counter(r["prediction"].get("decision_source", "unknown") for r in selected)),
                          "provider_failures": sum(r["prediction"].get("provider_ok") is not True for r in selected)}
        raw_scores = []
        for r in selected:
            raw, gold = r["prediction"].get("model_prediction"), r.get("expected_route", {})
            if raw is not None and gold.get("intent") in INTENTS:
                raw_scores.append(raw == gold)
        result[system]["raw_checkpoint_route"] = {"passed": sum(raw_scores), "scored": len(raw_scores)}
        from sklearn.metrics import f1_score
        result[system]["macro_f1"]={}
        for head,pred_key in (("intent","predicted_intent"),("agent","predicted_agent"),("action","predicted_next_action")):
            labelled=[r for r in selected if r.get("expected_route",{}).get(head) is not None]
            gold=[r["expected_route"][head] for r in labelled]
            pred=[r["prediction"].get(pred_key) or "prediction_failed" for r in labelled]
            result[system]["macro_f1"][head]=float(f1_score(gold,pred,labels=sorted(set(gold)),average="macro",zero_division=0)) if gold else None
        result[system]["answer_sources"]=dict(Counter(r["prediction"].get("answer_source","provider") for r in selected))
        from dusnx_core.constants import AGENTS,NEXT_ACTIONS
        result[system]["raw_checkpoint_macro_f1"]={}
        for head,vocabulary in (("intent",INTENTS),("agent",AGENTS),("action",NEXT_ACTIONS)):
            labelled=[r for r in selected if r["prediction"].get("model_prediction") is not None
                      and r.get("expected_route",{}).get(head) in vocabulary]
            gold=[r["expected_route"][head] for r in labelled]
            pred=[r["prediction"]["model_prediction"][head] for r in labelled]
            result[system]["raw_checkpoint_macro_f1"][head]={"scored":len(gold),
                "macro_f1":float(f1_score(gold,pred,labels=vocabulary,average="macro",zero_division=0)) if gold else None}
    return result


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--benchmark", default="benchmarks/week3_personalization_pilot.jsonl")
    ap.add_argument("--output-dir", default="runtime/week3-pilot")
    ap.add_argument("--provider", default="ollama", choices=["mock", "ollama"])
    ap.add_argument("--device", default="cpu", choices=["auto", "cpu", "cuda"])
    ap.add_argument("--validate-only", action="store_true")
    ap.add_argument("--checkpoint")
    ap.add_argument("--holdout-manifest")
    ap.add_argument("--include-no-state", action="store_true")
    ap.add_argument("--include-model-only", action="store_true")
    ap.add_argument("--all-systems", action="store_true")
    args = ap.parse_args()
    import torch
    torch.set_num_threads(2)
    rows = read_pilot(args.benchmark)
    if any(r.partition=="holdout" for r in rows):
        if not args.holdout_manifest:raise ValueError("holdout requires locked manifest")
        from dusnx_core.data_pipeline import verify_lock
        verify_lock(args.benchmark,args.holdout_manifest)
    if args.validate_only:
        print(f"Valid: {len(rows)} steps / {len({r.sequence_id for r in rows})} sequences")
        return
    os.environ["DUSNX_PROVIDER"], os.environ["DUSNX_DEVICE"] = args.provider, args.device
    if args.checkpoint:
        if not Path(args.checkpoint).is_file():raise ValueError("checkpoint unavailable")
        os.environ["DUSNX_CHECKPOINT"]=args.checkpoint
    systems_list = list(SYSTEMS)
    if args.all_systems:
        systems = ("baseline_a", "baseline_b", "model_only", "dusnx_no_state", "dusnx")
    else:
        if args.include_model_only:
            systems_list.append("model_only")
        if args.include_no_state:
            systems_list.append("dusnx_no_state")
        systems = tuple(systems_list)
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    if (out_dir/"predictions.jsonl").exists():raise ValueError("choose a new output directory; preserve earlier evidence")
    # Unique scratch directory; never delete earlier runs or user databases.
    scratch = REPO_ROOT / "runtime/week3-scratch" / secrets.token_hex(8)
    scratch.mkdir(parents=True)
    os.environ["DUSNX_DATA_DIR"] = str(scratch)
    from fastapi.testclient import TestClient
    import apps.ai_api.main as main_mod
    from apps.ai_api.provider import generate_response
    sequences = defaultdict(list)
    for row in rows:
        sequences[row.sequence_id].append(row)
    records = []
    with TestClient(main_mod.app) as client, (out_dir / "predictions.jsonl").open("w", encoding="utf-8") as fh:
        for seq, steps in sequences.items():
            inputs = [s.prediction_input() for s in steps]
            for system in systems:
                try:
                    if system == "model_only":
                        predictions = run_dusnx(inputs, client, main_mod, no_state=False, model_only=True)
                    elif system == "dusnx_no_state":
                        predictions = run_dusnx(inputs, client, main_mod, no_state=True, model_only=False)
                    elif system == "dusnx":
                        predictions = run_dusnx(inputs, client, main_mod, no_state=False, model_only=False)
                    else:
                        predictions = run_baseline(inputs, generate_response, static_memory=system == "baseline_b")
                except Exception as exc:
                    predictions = [dict(reply="", provider_ok=False, error=type(exc).__name__,
                                        decision_source="unknown") for _ in inputs]

                for step, pred in zip(steps, predictions, strict=True):
                    metrics, diagnosis = score_turn(step.model_dump(), pred)
                    record = dict(case_id=step.case_id, sequence_id=seq, step=step.step, system=system,
                                  input=step.prediction_input(), prediction=pred, metrics=metrics, diagnosis=diagnosis)
                    record["expected_route"] = dict(intent=step.expected_intent, agent=step.expected_agent,
                                                    action=step.expected_next_action)
                    records.append(record)
                    fh.write(json.dumps(record, ensure_ascii=False) + "\n")
                    fh.flush()
                print(f"Completed {seq}: {system}", flush=True)
    summary = dict(timestamp_utc=datetime.now(timezone.utc).isoformat(), provider=args.provider,
        benchmark_sha256=hashlib.sha256(Path(args.benchmark).read_bytes()).hexdigest(),
        checkpoint_sha256=hashlib.sha256(Path(main_mod.LOADED_CHECKPOINT).read_bytes()).hexdigest()
        if main_mod.LOADED_CHECKPOINT else None,
        runtime_mode=main_mod.RUNTIME_MODE, model_version=main_mod.MODEL_VERSION,
        review_status="not_independently_reviewed", step_count=len(rows), sequence_count=len(sequences),
        systems=aggregate(records))
    cases = []
    for seq in sequences:
        for system in systems:
            selected = [r for r in records if r["sequence_id"] == seq and r["system"] == system]
            scored = [v for r in selected for v in r["metrics"].values() if v is not None]
            cases.append(dict(sequence_id=seq, system=system, passed=all(scored),
                failed_steps=[r["case_id"] for r in selected if False in r["metrics"].values()]))
    errors = [r for r in records if False in r["metrics"].values() or r["prediction"].get("error")]
    for filename, data in (("summary.json", summary), ("cases.json", cases), ("errors.json", errors)):
        (out_dir / filename).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = ["| Metric | " + " | ".join(systems) + " |", "|---|" + "---:|" * len(systems)]
    sample_sys = "dusnx" if "dusnx" in summary["systems"] else next(iter(summary["systems"]))
    for key in summary["systems"][sample_sys]["metrics"]:
        cells = []
        for system in systems:
            m = summary["systems"][system]["metrics"][key]
            if m["scored"]:
                ci_str = f" [{m['ci_95'][0]:.2f}, {m['ci_95'][1]:.2f}]" if m.get("ci_95") else ""
                cells.append(f"{m['passed']}/{m['scored']} ({m['rate']:.1%}){ci_str}")
            else:
                cells.append("unlabelled")
        lines.append("| " + " | ".join([key, *cells]) + " |")
    for head in ("intent", "agent", "action"):
        cells = []
        for system in systems:
            val = summary["systems"][system]["macro_f1"].get(head)
            cells.append(f"{val:.3f}" if val is not None else "N/A")
        lines.append("| " + " | ".join([f"{head}_macro_f1", *cells]) + " |")
    (out_dir / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    print("\n".join(lines))
    print(f"Output: {out_dir}; labels not independently reviewed; mock is pipeline-only.")
    if any(s["provider_failures"] for s in summary["systems"].values()):
        raise SystemExit(1)
    if args.holdout_manifest:
        verify_lock(args.benchmark,args.holdout_manifest)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
