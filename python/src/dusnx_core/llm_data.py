"""Contracts and audits for the isolated LLM SFT dataset."""
from collections import Counter
import csv
from difflib import SequenceMatcher
import hashlib
import io
import json
from pathlib import Path
import re
import statistics
import unicodedata
from datetime import datetime

PROTECTED_PATH_PARTS = ("holdout", "reviewer", "submission", "benchmark", "training-results")
REVIEW_STATES = {"needs_human_review", "human_reviewed"}
SOURCES = {"synthetic_designed", "human_designed"}
RESPONSE_MODES = {"answer", "clarify", "acknowledge"}
VI_MARKERS = {"bạn", "mình", "tôi", "là", "và", "đã", "đang", "chưa", "không", "cần", "theo", "hiện", "được", "với", "của", "cho", "hãy", "vẫn", "này", "để"}
EN_MARKERS = {"the", "is", "are", "you", "your", "please", "what", "which", "how", "current", "saved", "answer", "decision", "returned", "timeout", "operation", "confirmed", "successful"}


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def write_json(path, value):
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


def normalized(value):
    return " ".join(unicodedata.normalize("NFC", value).casefold().split())

_NEGATION_MARKER = re.compile(
    r"\b(?:không|chưa|chẳng|chớ|not|never|no|without|cannot|can't|"
    r"didn't|doesn't|hasn't|haven't|isn't|aren't|wasn't|weren't)\b"
)
_NEGATION_CLAUSE_BOUNDARY = re.compile(
    r"[.!?;:\n]|\b(?:nhưng|tuy nhiên|song|but|however)\b"
)


def _forbidden_fact_is_asserted(answer, fact):
    """Treat a forbidden phrase in an explicit denial as a mention, not a claim."""
    start = 0
    while True:
        index = answer.find(fact, start)
        if index < 0:
            return False
        preceding = answer[max(0, index - 120):index]
        clause = _NEGATION_CLAUSE_BOUNDARY.split(preceding)[-1]
        if re.search(r"\b(?:không\s+chỉ|not\s+only)\b", clause):
            start = index + len(fact)
            continue
        if not _NEGATION_MARKER.search(clause):
            return True
        start = index + len(fact)


def _words(value):
    return re.findall(r"\w+", normalized(value), flags=re.UNICODE)


def _looks_vietnamese(value):
    words = _words(value)
    accents = len(re.findall(r"[ăâđêôơưáàảãạấầẩẫậắằẳẵặéèẻẽẹếềểễệíìỉĩịóòỏõọốồổỗộớờởỡợúùủũụứừửữựýỳỷỹỵ]", normalized(value)))
    return bool(words) and (accents > 0 or len(VI_MARKERS.intersection(words)) >= 2)


def _looks_english(value):
    words = _words(value)
    return bool(words) and len(EN_MARKERS.intersection(words)) >= 2 and not _looks_vietnamese(value)


def _content(messages):
    return "\n".join(message["content"] for message in messages)


def _prompt_signature(messages):
    pieces = []
    for message in messages:
        if message["role"] == "system":
            if "Bối cảnh giả lập:" in message["content"]:
                pieces.append(message["content"].split("Bối cảnh giả lập:", 1)[1])
        elif message["role"] == "user":
            pieces.append(message["content"])
    return normalized(" ".join(pieces))


def _ngrams(value, size=3):
    words = _words(value)
    return {tuple(words[index:index + size]) for index in range(max(0, len(words) - size + 1))}


def near_similarity(left, right):
    left, right = normalized(left), normalized(right)
    sequence = SequenceMatcher(None, left, right).ratio()
    left_grams, right_grams = _ngrams(left), _ngrams(right)
    jaccard = len(left_grams & right_grams) / len(left_grams | right_grams) if left_grams | right_grams else 0.0
    return max(sequence, jaccard)


def read_sft(path, split):
    path = Path(path)
    if any(part in str(path.resolve()).casefold() for part in PROTECTED_PATH_PARTS):
        raise ValueError("Protected data location is not an SFT input")
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    validate(rows, split)
    return rows


def validate(rows, split):
    ids = set()
    required = ("id", "source", "source_revision", "license", "generation_method", "scenario_family", "sequence_id", "user_id", "split", "review_status", "messages", "data_kind", "quality_contracts")
    for row in rows:
        if any(row.get(key) in (None, "", []) for key in required):
            raise ValueError("Missing SFT provenance/messages/quality contract")
        if row["id"] in ids:
            raise ValueError("Duplicate record ID")
        ids.add(row["id"])
        if row["split"] != split:
            raise ValueError("Unexpected split")
        if row["source"] not in SOURCES or row["license"] != "CC0-1.0":
            raise ValueError("Source or license is not approved")
        expected_method = "AI-generated" if row["source"] == "synthetic_designed" else "human-authored"
        if row["generation_method"] != expected_method:
            raise ValueError("Generation method conflicts with source")
        if row["review_status"] not in REVIEW_STATES:
            raise ValueError("Invalid review status")
        if not row["user_id"].startswith("fictional-"):
            raise ValueError("Only fictional identities accepted")
        if row["data_kind"] != "designed_conversation":
            raise ValueError("Do not mislabel observed conversations")
        messages = row["messages"]
        if not isinstance(messages, list) or len(messages) < 3:
            raise ValueError("Conversation is too short")
        roles = [message.get("role") for message in messages]
        if roles[0] != "system" or roles[-1] != "assistant" or roles[1:] != ["user", "assistant"] * ((len(roles) - 1) // 2):
            raise ValueError("Invalid system/user/assistant ordering")
        for message in messages:
            text = message.get("content", "")
            if not isinstance(text, str) or not text.strip():
                raise ValueError("Empty message")
            if re.search(r"(?i)(bearer\s+\S+|[\w.+-]+@[\w.-]+\.[a-z]{2,}|\b\d{9,}\b|gh[pous]_[a-z0-9]{12,})", text):
                raise ValueError("Potential personal data or secret")
        if any(key.startswith(("gold_", "expected_", "prediction")) for key in row) and split != "test":
            raise ValueError("Evaluation labels in training")
        assistant_indexes = [index for index, message in enumerate(messages) if message["role"] == "assistant"]
        contracts = row["quality_contracts"]
        if len(contracts) != len(assistant_indexes):
            raise ValueError("One quality contract is required per assistant turn")
        for turn_number, (message_index, contract) in enumerate(zip(assistant_indexes, contracts), 1):
            if contract.get("assistant_turn") != turn_number or contract.get("response_mode") not in RESPONSE_MODES:
                raise ValueError("Invalid assistant turn contract")
            language = contract.get("response_language", contract.get("language"))
            if language not in {"vi", "en"}:
                raise ValueError("Vietnamese or English output contract required")
            for field in ("required_facts", "forbidden_facts", "future_facts"):
                if not isinstance(contract.get(field), list) or any(not isinstance(value, str) or not value.strip() for value in contract[field]):
                    raise ValueError(f"Invalid {field} contract")
            prefix = normalized(_content(messages[:message_index]))
            answer = normalized(messages[message_index]["content"])
            suffix = normalized(_content(messages[message_index + 1:]))
            for fact in contract["required_facts"]:
                fact = normalized(fact)
                if fact not in prefix or fact not in answer:
                    raise ValueError(f"{row['id']} turn {turn_number}: required fact is unsupported or missing: {fact}")
            for fact in contract["forbidden_facts"]:
                fact = normalized(fact)
                if _forbidden_fact_is_asserted(answer, fact):
                    raise ValueError(f"{row['id']} turn {turn_number}: obsolete/rejected fact leaked: {fact}")
            for fact in contract["future_facts"]:
                fact = normalized(fact)
                if fact in prefix or fact not in suffix or fact in answer:
                    raise ValueError(f"{row['id']} turn {turn_number}: future fact leaked: {fact}")
            if contract["response_mode"] == "clarify" and "?" not in messages[message_index]["content"]:
                raise ValueError(f"{row['id']} turn {turn_number}: clarification response must ask a question")
            language_ok = (_looks_vietnamese(messages[message_index]["content"]) if language == "vi"
                           else _looks_english(messages[message_index]["content"]))
            if not language_ok:
                raise ValueError(f"Assistant answer does not match response_language={language}")
    if not rows:
        raise ValueError("Empty partition")


def completion_rows(rows):
    """Each assistant turn receives only preceding context, never future turns."""
    result = []
    for row in rows:
        turn = 0
        for index, message in enumerate(row["messages"]):
            if message["role"] == "assistant":
                turn += 1
                result.append({"prompt": row["messages"][:index], "completion": [message], "record_id": row["id"], "assistant_turn": turn})
    return result


def _near_duplicate_pairs(partitions, threshold):
    prompts = []
    for split, rows in partitions.items():
        for row in rows:
            for pair in completion_rows([row]):
                prompts.append((split, row["id"], pair["assistant_turn"], _prompt_signature(pair["prompt"])))
    matches, max_cross_split = [], 0.0
    for index, left in enumerate(prompts):
        for right in prompts[index + 1:]:
            score = near_similarity(left[3], right[3])
            if left[0] != right[0]:
                max_cross_split = max(max_cross_split, score)
            if score >= threshold:
                matches.append({"left": {"split": left[0], "id": left[1], "assistant_turn": left[2]}, "right": {"split": right[0], "id": right[1], "assistant_turn": right[2]}, "score": round(score, 4), "cross_split": left[0] != right[0]})
    return matches, max_cross_split


def audit(partitions, tokenizer=None, max_length=None, near_duplicate_threshold=0.82):
    seen = {key: set() for key in ("id", "sequence_id", "user_id", "scenario_family", "prompt")}
    report = {}
    for split, rows in partitions.items():
        validate(rows, split)
        pairs = completion_rows(rows)
        prompts = [normalized(json.dumps(pair["prompt"], ensure_ascii=False, sort_keys=True)) for pair in pairs]
        values = {key: {row[key] for row in rows} for key in ("id", "sequence_id", "user_id", "scenario_family")}
        values["prompt"] = set(prompts)
        for key, current in values.items():
            if seen[key] & current:
                raise ValueError(f"Cross-split leakage: {key}")
            seen[key] |= current
        if len(set(prompts)) != len(prompts):
            raise ValueError("Duplicate prompt within split")
        char_lengths = [sum(len(message["content"]) for message in row["messages"]) for row in rows]
        token_lengths = []
        if tokenizer is not None:
            for pair in pairs:
                token_count = len(tokenizer.apply_chat_template(pair["prompt"] + pair["completion"], tokenize=True))
                token_lengths.append(token_count)
                if max_length is not None and token_count > max_length:
                    raise ValueError(f"Completion would be truncated: {pair['record_id']} turn {pair['assistant_turn']} has {token_count} tokens")
        report[split] = {"sequences": len(values["sequence_id"]), "records": len(rows), "assistant_pairs": len(pairs), "unique_prompts": len(set(prompts)), "duplicate_prompt_rate": 1 - len(set(prompts)) / len(prompts), "scenario_distribution": dict(sorted(Counter(row["scenario_family"] for row in rows).items())), "char_length": {"min": min(char_lengths), "max": max(char_lengths), "mean": round(statistics.mean(char_lengths), 2)}, "token_length": ({"min": min(token_lengths), "max": max(token_lengths), "mean": round(statistics.mean(token_lengths), 2)} if token_lengths else None), "sources": dict(Counter(row["source"] for row in rows)), "review_status": dict(Counter(row["review_status"] for row in rows)), "response_modes": dict(Counter(contract["response_mode"] for row in rows for contract in row["quality_contracts"]))}
    near_duplicates, max_cross_split = _near_duplicate_pairs(partitions, near_duplicate_threshold)
    cross_split = [match for match in near_duplicates if match["cross_split"]]
    if cross_split:
        sample = cross_split[0]
        raise ValueError(f"Cross-split near duplicate: {sample['left']['id']} vs {sample['right']['id']} ({sample['score']})")
    report["quality"] = {"near_duplicate_threshold": near_duplicate_threshold, "near_duplicate_pairs_within_split": near_duplicates, "max_cross_split_similarity": round(max_cross_split, 4), "human_review_complete": all(row["review_status"] == "human_reviewed" for rows in partitions.values() for row in rows)}
    return report


def verify_file_manifest(root, manifest):
    root = Path(root).resolve()
    for name, expected in manifest["files"].items():
        if Path(name).is_absolute() or "\\" in name or ":" in name or ".." in Path(name).parts:
            raise ValueError("Unsafe artifact path")
        raw = root / name
        if any(path.is_symlink() for path in [raw, *raw.parents] if path != root.parent):
            raise ValueError("Symlink artifact")
        path = raw.resolve()
        if not path.is_relative_to(root):
            raise ValueError("Unsafe artifact path")
        if not path.is_file() or digest(path) != expected:
            raise ValueError(f"Artifact checksum mismatch: {name}")
    return True


def verify_train_validation_lineage_receipt(root, receipt, expected_files, expected_rows):
    """Verify a v2 aggregate receipt against its parent and approved supplement artifacts."""
    root = Path(root).resolve()
    lineage = receipt.get("lineage") if isinstance(receipt, dict) else None
    expected_paths = {
        "parent_manifest": "lineage_parent_manifest.json",
        "parent_receipt": "lineage_parent_train_validation_review_receipt.json",
        "parent_train": "lineage_parent_train.jsonl",
        "parent_validation": "lineage_parent_validation.jsonl",
        "supplement_receipt": "supplement_review_receipt.json",
        "supplement_review_csv": "supplement_review.csv",
    }

    def read_artifact(key):
        if not isinstance(lineage, dict) or lineage.get(f"{key}_path") != expected_paths[key]:
            raise ValueError("Invalid train/validation receipt lineage path")
        path = root / expected_paths[key]
        if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(root):
            raise ValueError("Missing or unsafe train/validation lineage artifact")
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != lineage.get(f"{key}_sha256"):
            raise ValueError("Train/validation lineage artifact hash mismatch")
        return raw

    if (
        receipt.get("schema_version") != 2
        or receipt.get("receipt_kind") != "lineage_aggregate"
        or receipt.get("review_type") != "train_validation"
        or receipt.get("test_only") is not False
        or receipt.get("result_files") != expected_files
        or type(receipt.get("row_count")) is not int
        or receipt.get("row_count") != expected_rows
    ):
        raise ValueError("Invalid lineage-aware train/validation receipt")

    parent_manifest_raw = read_artifact("parent_manifest")
    parent_receipt_raw = read_artifact("parent_receipt")
    parent_train_raw = read_artifact("parent_train")
    parent_validation_raw = read_artifact("parent_validation")
    supplement_receipt_raw = read_artifact("supplement_receipt")
    review_csv_raw = read_artifact("supplement_review_csv")
    try:
        parent_manifest = json.loads(parent_manifest_raw.decode("utf-8"))
        parent_receipt = json.loads(parent_receipt_raw.decode("utf-8"))
        supplement = json.loads(supplement_receipt_raw.decode("utf-8"))
        final_train_raw = (root / "train.jsonl").read_bytes()
        final_validation_raw = (root / "validation.jsonl").read_bytes()
    except (UnicodeDecodeError, json.JSONDecodeError, OSError) as exc:
        raise ValueError("Invalid train/validation lineage data") from exc

    parent_files = {
        "train.jsonl": hashlib.sha256(parent_train_raw).hexdigest(),
        "validation.jsonl": hashlib.sha256(parent_validation_raw).hexdigest(),
    }
    counts = lineage.get("completion_counts") if isinstance(lineage, dict) else None
    if (
        not isinstance(parent_manifest, dict)
        or parent_manifest.get("status") != "human_attested_locked_before_training"
        or parent_manifest.get("locked") is not True
        or any(parent_manifest.get("files", {}).get(name) != value for name, value in parent_files.items())
        or not isinstance(parent_receipt, dict)
        or type(parent_receipt.get("schema_version")) is not int
        or parent_receipt.get("schema_version") != 1
        or parent_receipt.get("review_type") != "train_validation"
        or parent_receipt.get("test_only") is not False
        or parent_receipt.get("result_files") != parent_files
        or type(parent_receipt.get("row_count")) is not int
        or not isinstance(supplement, dict)
        or type(supplement.get("schema_version")) is not int
        or supplement.get("schema_version") != 1
        or supplement.get("receipt_type") != "train_validation_supplement_review"
        or supplement.get("scope") != "supplemental completion rows only; does not attest the full release"
        or supplement.get("not_a_full_release_receipt") is not True
        or supplement.get("release_v3_sha256") != expected_files
        or supplement.get("parent_manifest_sha256") != hashlib.sha256(parent_manifest_raw).hexdigest()
        or supplement.get("parent_train_validation_receipt_sha256") != hashlib.sha256(parent_receipt_raw).hexdigest()
        or supplement.get("parent_file_sha256") != parent_files
        or not isinstance(counts, dict)
        or counts.get("parent") != parent_receipt.get("row_count")
        or counts.get("supplement") != supplement.get("covered_completion_rows")
        or type(counts.get("total")) is not int
        or counts["total"] != counts["parent"] + counts["supplement"]
        or counts["total"] != expected_rows
        or final_train_raw[:len(parent_train_raw)] != parent_train_raw
        or final_validation_raw[:len(parent_validation_raw)] != parent_validation_raw
    ):
        raise ValueError("Train/validation receipt lineage does not match parent and supplement")

    csv_hash = hashlib.sha256(review_csv_raw).hexdigest()
    if supplement.get("review_csv_sha256") != csv_hash:
        raise ValueError("Supplement review CSV hash mismatch")
    expected_release_hashes = {
        "train.jsonl": hashlib.sha256(final_train_raw).hexdigest(),
        "validation.jsonl": hashlib.sha256(final_validation_raw).hexdigest(),
    }
    if expected_release_hashes != expected_files:
        raise ValueError("Lineage receipt release hashes do not match current data")

    try:
        parent_train_rows = [json.loads(line) for line in parent_train_raw.decode("utf-8").splitlines() if line.strip()]
        parent_validation_rows = [json.loads(line) for line in parent_validation_raw.decode("utf-8").splitlines() if line.strip()]
        final_train_rows = [json.loads(line) for line in final_train_raw.decode("utf-8").splitlines() if line.strip()]
        final_validation_rows = [json.loads(line) for line in final_validation_raw.decode("utf-8").splitlines() if line.strip()]
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Invalid JSONL in train/validation lineage") from exc
    if any(
        not isinstance(row, dict)
        for rows in (parent_train_rows, parent_validation_rows, final_train_rows, final_validation_rows)
        for row in rows
    ):
        raise ValueError("Invalid JSONL record in train/validation lineage")
    additions = {
        "train": final_train_rows[len(parent_train_rows):],
        "validation": final_validation_rows[len(parent_validation_rows):],
    }
    def assistant_completion_count(rows):
        total = 0
        for record in rows:
            messages = record.get("messages")
            if not isinstance(messages, list):
                continue
            total += sum(
                1
                for message in messages
                if isinstance(message, dict) and message.get("role") == "assistant"
            )
        return total

    parent_completion_count = assistant_completion_count(parent_train_rows) + assistant_completion_count(parent_validation_rows)
    added_completion_count = assistant_completion_count(additions["train"]) + assistant_completion_count(additions["validation"])
    if (
        type(parent_receipt.get("row_count")) is not int
        or parent_receipt["row_count"] != parent_completion_count
        or type(supplement.get("covered_completion_rows")) is not int
        or supplement["covered_completion_rows"] != added_completion_count
        or not isinstance(supplement.get("added_records"), dict)
        or supplement["added_records"] != {split: len(rows) for split, rows in additions.items()}
        or not isinstance(supplement.get("release_counts"), dict)
        or supplement["release_counts"] != {
            "train_records": len(final_train_rows),
            "train_assistant_completions": assistant_completion_count(final_train_rows),
            "validation_records": len(final_validation_rows),
            "validation_assistant_completions": assistant_completion_count(final_validation_rows),
        }
    ):
        raise ValueError("Train/validation lineage completion or record counts mismatch")
    if (
        len(final_train_rows) <= len(parent_train_rows)
        or len(final_validation_rows) <= len(parent_validation_rows)
        or any(old != new for old, new in zip(parent_train_rows, final_train_rows))
        or any(old != new for old, new in zip(parent_validation_rows, final_validation_rows))
        or any(row.get("review_status") != "human_reviewed" for rows in additions.values() for row in rows)
    ):
        raise ValueError("Parent train/validation rows changed or supplement rows are not reviewed")

    expected_review = {}
    try:
        for split, rows in additions.items():
            for record in rows:
                messages = record["messages"]
                if not isinstance(messages, list) or not isinstance(record["id"], str):
                    raise ValueError("Invalid supplement record structure in lineage")
                turn = 0
                for index, message in enumerate(messages):
                    if not isinstance(message, dict):
                        raise ValueError("Invalid supplement record structure in lineage")
                    if message.get("role") != "assistant":
                        continue
                    turn += 1
                    expected_review[f"{split}:{record['id']}:{turn}"] = {
                        "split": split,
                        "record_id": record["id"],
                        "assistant_turn": str(turn),
                        "prefix_json": json.dumps(messages[:index], ensure_ascii=False, separators=(",", ":")),
                        "reference_answer": message["content"],
                        "quality_contract_json": json.dumps(record["quality_contracts"][turn - 1], ensure_ascii=False, separators=(",", ":")),
                    }
    except (KeyError, TypeError, IndexError) as exc:
        raise ValueError("Invalid supplement record structure in lineage") from exc
    covered_keys = supplement.get("covered_review_keys")
    if (
        not isinstance(covered_keys, list)
        or any(not isinstance(key, str) for key in covered_keys)
        or len(covered_keys) != len(set(covered_keys))
        or set(covered_keys) != set(expected_review)
    ):
        raise ValueError("Supplement review keys do not match added completions")
    try:
        review_rows = list(csv.DictReader(io.StringIO(review_csv_raw.decode("utf-8-sig", errors="strict"))))
    except (UnicodeDecodeError, csv.Error) as exc:
        raise ValueError("Invalid supplement review CSV") from exc
    supplement_reviewers = supplement.get("reviewers")
    supplement_times = supplement.get("reviewed_at")
    parent_reviewers = parent_receipt.get("reviewers")
    parent_times = parent_receipt.get("reviewed_at")
    if any(
        not isinstance(values, list)
        or not values
        or any(not isinstance(value, str) or not value.strip() for value in values)
        for values in (supplement_reviewers, supplement_times, parent_reviewers, parent_times)
    ):
        raise ValueError("Invalid lineage reviewer provenance")
    review_by_key = {row.get("review_key", ""): row for row in review_rows}
    if len(review_rows) != len(expected_review) or len(review_by_key) != len(expected_review) or set(review_by_key) != set(expected_review):
        raise ValueError("Supplement review CSV keys do not match lineage receipt")
    csv_reviewers = set()
    csv_times = set()
    for key, source in expected_review.items():
        row = review_by_key[key]
        if any(row.get(field) != value for field, value in source.items()):
            raise ValueError("Supplement review CSV immutable source column changed")
        if row.get("decision", "").strip().casefold() != "approve" or row.get("revised_answer", "").strip() or row.get("revised_quality_contract_json", "").strip():
            raise ValueError("Supplement review CSV approval does not match reviewed release")
        reviewer = row.get("reviewer", "").strip()
        timestamp = row.get("reviewed_at", "").strip()
        try:
            parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("Invalid supplement review timestamp") from exc
        if parsed.tzinfo is None or reviewer not in supplement_reviewers:
            raise ValueError("Supplement reviewer or timestamp mismatch")
        csv_reviewers.add(reviewer)
        csv_times.add(timestamp)

    if (
        csv_reviewers != set(supplement_reviewers)
        or csv_times != set(supplement_times)
        or supplement.get("decisions") != {"approve": len(expected_review), "revise": 0}
    ):
        raise ValueError("Supplement receipt reviewer, timestamp, or decision summary mismatch")

    expected_reviewers = sorted(set(parent_reviewers) | set(supplement_reviewers))
    expected_times = sorted(set(parent_times) | set(supplement_times))
    if receipt.get("reviewers") != expected_reviewers or receipt.get("reviewed_at") != expected_times:
        raise ValueError("Aggregate reviewer provenance does not match its source receipts")
    return True


def verify_full_training_gate(root, manifest):
    """Verify the human-only release gate without reading frozen test examples."""
    root = Path(root)
    if not isinstance(manifest, dict) or (
        type(manifest.get("schema_version")) is not int
        or manifest.get("schema_version") != 4
        or manifest.get("status") != "human_attested_locked_before_training"
        or manifest.get("locked") is not True
    ):
        raise ValueError("Full SFT requires the human-attested locked manifest")
    files = manifest.get("files")
    row_counts = manifest.get("row_counts")
    expected_file_names = {
        "train.jsonl", "validation.jsonl", "test.jsonl",
        "train_validation_review_receipt.json", "independent_test_review_receipt.json",
    }
    if (
        not isinstance(files, dict)
        or set(files) != expected_file_names
        or any(not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value) for value in files.values())
        or not isinstance(row_counts, dict)
        or set(row_counts) != {"train", "validation", "test"}
        or any(type(value) is not int or value <= 0 for value in row_counts.values())
    ):
        raise ValueError("Invalid locked data manifest schema")
    attestation_path = root / "human_test_attestation.json"
    if not attestation_path.is_file():
        raise ValueError("Full SFT requires a human test attestation")
    attestation = json.loads(attestation_path.read_text(encoding="utf-8"))
    if not isinstance(attestation, dict):
        raise ValueError("Invalid independent human data attestation")
    author_value = attestation.get("human_author")
    reviewer_value = attestation.get("reviewer")
    if not isinstance(author_value, str) or not isinstance(reviewer_value, str):
        raise ValueError("Invalid independent human data attestation")
    author = author_value.strip()
    reviewer = reviewer_value.strip()
    expected_test_hash = files["test.jsonl"]
    if (
        not author
        or not reviewer
        or author == reviewer
        or attestation.get("training_reviewed") is not True
        or attestation.get("locked_before_training") is not True
        or not expected_test_hash
        or attestation.get("test_sha256") != expected_test_hash
    ):
        raise ValueError("Invalid independent human data attestation")
    receipt_specs = (
        ("train_validation_review_receipt.json", "train_review_receipt_sha256", "train_validation", {name: files[name] for name in ("train.jsonl", "validation.jsonl")}, row_counts["train"] + row_counts["validation"]),
        ("independent_test_review_receipt.json", "test_review_receipt_sha256", "independent_test", {"test.jsonl": expected_test_hash}, row_counts["test"]),
    )
    for name, attestation_key, review_type, result_files, expected_rows in receipt_specs:
        receipt_path = root / name
        receipt_hash = str(attestation.get(attestation_key, ""))
        if not re.fullmatch(r"[0-9a-f]{64}", receipt_hash) or files.get(name) != receipt_hash:
            raise ValueError("Missing or invalid human review receipt")
        try:
            receipt_raw = receipt_path.read_bytes()
            if hashlib.sha256(receipt_raw).hexdigest() != receipt_hash:
                raise ValueError("Missing or invalid human review receipt")
            receipt = json.loads(receipt_raw.decode("utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("Missing or invalid human review receipt") from exc
        if not isinstance(receipt, dict):
            raise ValueError("Missing or invalid human review receipt")
        receipt_version = receipt.get("schema_version")
        if review_type == "train_validation" and type(receipt_version) is int and receipt_version == 2:
            try:
                verify_train_validation_lineage_receipt(root, receipt, result_files, expected_rows)
            except ValueError as exc:
                raise ValueError("Missing or invalid lineage-aware train/validation receipt") from exc
        reviewers = receipt.get("reviewers")
        reviewed_at = receipt.get("reviewed_at")
        if (
            type(receipt_version) is not int
            or receipt_version not in (1, 2)
            or (receipt_version == 2 and review_type != "train_validation")
            or receipt.get("review_type") != review_type
            or receipt.get("test_only") is not False
            or receipt.get("result_files") != result_files
            or type(receipt.get("row_count")) is not int
            or receipt["row_count"] != expected_rows
            or not isinstance(reviewers, list)
            or not reviewers
            or any(not isinstance(value, str) or not value.strip() for value in reviewers)
            or not isinstance(reviewed_at, list)
            or not reviewed_at
            or any(not isinstance(value, str) or not value.strip() for value in reviewed_at)
        ):
            raise ValueError("Missing or invalid human review receipt")
        if reviewer not in reviewers:
            raise ValueError("Review receipt reviewer does not match human attestation")
        if review_type == "independent_test" and (
            receipt.get("human_author") != author or reviewer == author
        ):
            raise ValueError("Invalid independent human data attestation")
    return True
