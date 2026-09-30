"""Contracts and audits for the isolated LLM SFT dataset."""
from collections import Counter
from difflib import SequenceMatcher
import hashlib
import json
from pathlib import Path
import re
import statistics
import unicodedata

PROTECTED_PATH_PARTS = ("holdout", "reviewer", "submission", "benchmark", "training-results")
REVIEW_STATES = {"needs_human_review", "human_reviewed"}
SOURCES = {"synthetic_designed", "human_designed"}
RESPONSE_MODES = {"answer", "clarify", "acknowledge"}
VI_MARKERS = {"bạn", "mình", "tôi", "là", "và", "đã", "đang", "chưa", "không", "cần", "theo", "hiện", "được", "với", "của", "cho", "hãy", "vẫn", "này", "để"}


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


def _words(value):
    return re.findall(r"\w+", normalized(value), flags=re.UNICODE)


def _looks_vietnamese(value):
    words = _words(value)
    accents = len(re.findall(r"[ăâđêôơưáàảãạấầẩẫậắằẳẵặéèẻẽẹếềểễệíìỉĩịóòỏõọốồổỗộớờởỡợúùủũụứừửữựýỳỷỹỵ]", normalized(value)))
    return bool(words) and (accents > 0 or len(VI_MARKERS.intersection(words)) >= 2)


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
            if contract.get("language") != "vi":
                raise ValueError("Vietnamese output contract required")
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
                if fact not in prefix or fact in answer:
                    raise ValueError(f"{row['id']} turn {turn_number}: obsolete/rejected fact leaked: {fact}")
            for fact in contract["future_facts"]:
                fact = normalized(fact)
                if fact in prefix or fact not in suffix or fact in answer:
                    raise ValueError(f"{row['id']} turn {turn_number}: future fact leaked: {fact}")
            if contract["response_mode"] == "clarify" and "?" not in messages[message_index]["content"]:
                raise ValueError(f"{row['id']} turn {turn_number}: clarification response must ask a question")
            if not _looks_vietnamese(messages[message_index]["content"]):
                raise ValueError("Assistant answer is not detectably Vietnamese")
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


def verify_full_training_gate(root, manifest):
    """Verify the human-only release gate without reading frozen test examples."""
    root = Path(root)
    if manifest.get("status") != "human_attested_locked_before_training":
        raise ValueError("Full SFT requires the human-attested locked manifest")
    attestation_path = root / "human_test_attestation.json"
    if not attestation_path.is_file():
        raise ValueError("Full SFT requires a human test attestation")
    attestation = json.loads(attestation_path.read_text(encoding="utf-8"))
    author = str(attestation.get("human_author", "")).strip()
    reviewer = str(attestation.get("reviewer", "")).strip()
    expected_test_hash = manifest.get("files", {}).get("test.jsonl")
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
    return True
