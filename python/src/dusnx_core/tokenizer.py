import hashlib
import re
from typing import Iterable

TOKEN_RE = re.compile(r"[\wÀ-ỹ]+", re.UNICODE)


def tokenize(text: str) -> list[str]:
    return TOKEN_RE.findall((text or "").lower())


def stable_bucket(token: str, vocab_size: int) -> int:
    # Bucket 0 is PAD. Real tokens map to [1, vocab_size-1].
    digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
    value = int.from_bytes(digest, "little")
    return 1 + (value % max(1, vocab_size - 1))


def encode_text(text: str, vocab_size: int, max_tokens: int) -> list[int]:
    ids = [stable_bucket(tok, vocab_size) for tok in tokenize(text)[:max_tokens]]
    if len(ids) < max_tokens:
        ids.extend([0] * (max_tokens - len(ids)))
    return ids


def batch_encode(texts: Iterable[str], vocab_size: int, max_tokens: int) -> list[list[int]]:
    return [encode_text(t, vocab_size, max_tokens) for t in texts]
