"""Local retrieval index for grounded answers.

The chat model is small and has no project knowledge. This module indexes the
repository's documentation and code into SQLite FTS5 (trigram tokenizer, which
works for Vietnamese, English, identifiers, and mixed text without a word
segmenter) and returns passages with stable citations.

It intentionally has no network dependency and no embedding model: a 4 GB GPU
must stay free for the chat model, and retrieval must work offline.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import os
import re
import sqlite3
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

_SCHEMA_VERSION = "2"

_SCHEMA_BASE = """
CREATE TABLE IF NOT EXISTS rag_meta (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS rag_documents (
    doc_id TEXT PRIMARY KEY,
    path TEXT UNIQUE NOT NULL,
    title TEXT,
    kind TEXT,
    sha256 TEXT NOT NULL,
    size INTEGER NOT NULL,
    mtime REAL NOT NULL,
    chunks INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS rag_chunks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    doc_id TEXT NOT NULL,
    ordinal INTEGER NOT NULL,
    heading TEXT,
    start_line INTEGER,
    end_line INTEGER,
    text TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_rag_chunks_doc ON rag_chunks(doc_id);
"""

# text_norm/heading_norm hold the same content without Vietnamese diacritics so
# a query typed as "kien truc dusn" still matches "kiến trúc DUSN".
_SCHEMA_FTS = """
CREATE VIRTUAL TABLE IF NOT EXISTS rag_fts USING fts5(
    text, heading, text_norm, heading_norm, tokenize='trigram'
);
"""

_STOPWORDS = {
    "la", "là", "cua", "của", "va", "và", "cho", "voi", "với", "trong", "ngoai", "ngoài",
    "the", "and", "for", "with", "that", "this", "from", "what", "which", "how", "why",
    "when", "where", "who", "is", "are", "was", "were", "be", "been", "to", "of", "in",
    "on", "at", "it", "its", "as", "by", "or", "an", "a", "the", "do", "does", "did",
    "can", "could", "would", "should", "will", "thi", "thì", "ma",
    "mà", "nhu", "như", "the", "nào", "nao", "gi", "gì", "sao", "khong", "không", "co",
    "có", "duoc", "được", "hay", "hoac", "hoặc", "mot", "một", "cac", "các", "nhung",
    "những", "khi", "nếu", "neu", "để", "de", "về", "ve", "tôi", "toi", "ban", "bạn",
    "minh", "mình", "tao", "mày", "may", "hãy", "hay", "giúp", "giup", "cho", "biết",
    "biet", "nói", "noi", "làm", "lam", "ra", "sao", "thế", "the", "nay", "này",
    "do", "đó", "day", "đây", "khi", "lúc", "luc", "bao", "nhieu", "nhiêu",
    "gồm", "gom", "bao gồm", "bao gom", "dùng", "dung", "work", "works",
    "đâu", "dau", "ở", "o", "bằng", "bang",
    # Light verbs in "X hoạt động thế nào": they describe the question, not
    # the subject, and otherwise pull setup steps into functional answers.
    "hoạt", "hoat", "động", "dong",
    # Question framing. "câu hỏi" (a question), "đang" (currently) appear in
    # nearly every document and would otherwise inflate coverage on any query.
    "câu", "cau", "hỏi", "hoi", "đang", "dang",
}

_INDEX_PATTERNS = [
    "README.md", "WEEK3_HANDOFF.md", "PHASE1_1_UPDATE.md",
    "docs/**/*.md", "docs/**/*.html", "docs/**/*.txt",
    "web-ui/*.js", "web-ui/*.html", "web-ui/*.css",
    "gateway-dotnet/**/*.cs", "gateway-dotnet/**/*.csproj",
    "word-addin/*.js", "word-addin/*.json", "word-addin/*.html", "word-addin/*.css",
    "powerpoint-addin/*.js", "powerpoint-addin/*.json", "powerpoint-addin/*.html",
    "python/apps/**/*.py", "python/src/**/*.py",
    "scripts/*.py", "configs/*.yaml", "configs/**/*.yaml",
    "requirements/*.txt",
]

_SKIP_PARTS = {
    ".venv", "__pycache__", "node_modules", ".git", "runtime", "artifacts",
    "training-results", "backup-data-protected", "datasets", "benchmarks",
    "python/tests", "gateway-dotnet.tests", "scratch-lineage-verify-c0d714",
}

# Test sources match every product term but never answer a product question.
_SKIP_FILE = re.compile(
    r"(?:^|/)(?:test_[^/]*\.py|[^/]*_test\.py|[^/]*\.test\.(?:js|ts)|[^/]*\.spec\.(?:js|ts))$"
    # Generated scenario literals repeat product words without documenting the
    # product; quoting them answers questions with test fixtures.
    r"|(?:^|/)(?:designed_data|synthetic)[^/]*\.py$",
    re.IGNORECASE,
)

_KIND_BY_SUFFIX = {
    ".md": "markdown", ".html": "html", ".txt": "text", ".py": "python",
    ".js": "javascript", ".css": "css", ".cs": "csharp", ".json": "json",
    ".yaml": "yaml", ".yml": "yaml", ".csproj": "xml",
}


@dataclass
class Chunk:
    heading: str
    start_line: int
    end_line: int
    text: str


@dataclass
class Hit:
    path: str
    title: str
    heading: str
    start_line: int
    end_line: int
    text: str
    score: float
    rank: float = 0.0
    source_id: str = ""
    coverage: float = 0.0

    def as_source(self) -> dict:
        return {
            "id": self.source_id,
            "path": self.path,
            "title": self.title,
            "heading": self.heading,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "score": round(self.score, 4),
            "coverage": round(self.coverage, 3),
        }


def _repo_root() -> Path:
    return Path(os.getenv("DUSNX_RAG_ROOT", Path(__file__).resolve().parents[3])).resolve()


def database_path() -> Path:
    # The index is derived from repository files, not user data: it stays in the
    # repo so every runtime instance (including isolated test data dirs) sees it.
    configured = os.getenv("DUSNX_RAG_DB")
    if configured:
        return Path(configured).resolve()
    return _repo_root() / "python" / "data" / "rag.db"


def is_available() -> bool:
    path = database_path()
    if not path.exists():
        return False
    try:
        with _connect() as conn:
            count = conn.execute("SELECT COUNT(*) FROM rag_chunks").fetchone()[0]
        return count > 0
    except sqlite3.Error:
        return False


def index_status() -> dict:
    path = database_path()
    if not path.exists():
        return {"available": False, "path": str(path), "documents": 0, "chunks": 0, "built_at": None}
    try:
        with _connect() as conn:
            docs = conn.execute("SELECT COUNT(*) FROM rag_documents").fetchone()[0]
            chunks = conn.execute("SELECT COUNT(*) FROM rag_chunks").fetchone()[0]
            built = conn.execute("SELECT value FROM rag_meta WHERE key='built_at'").fetchone()
        return {"available": chunks > 0, "path": str(path), "documents": docs,
                "chunks": chunks, "built_at": built[0] if built else None}
    except sqlite3.Error as exc:
        return {"available": False, "path": str(path), "error": str(exc)}


def _connect() -> sqlite3.Connection:
    path = database_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(_SCHEMA_BASE)
    row = conn.execute("SELECT value FROM rag_meta WHERE key='schema'").fetchone()
    if row is None:
        conn.executescript(_SCHEMA_FTS)
    elif row[0] != _SCHEMA_VERSION:
        # The index is a derived artifact; rebuild it with the current schema
        # instead of migrating columns in place.
        conn.executescript("DROP TABLE IF EXISTS rag_fts; "
                           "DROP TABLE IF EXISTS rag_chunks; "
                           "DROP TABLE IF EXISTS rag_documents;")
        conn.executescript(_SCHEMA_BASE)
        conn.executescript(_SCHEMA_FTS)
        conn.execute("INSERT INTO rag_meta(key,value) VALUES('schema',?) "
                     "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                     (_SCHEMA_VERSION,))
        conn.commit()
    return conn


def _strip_diacritics(text: str) -> str:
    """Lowercase and fold Vietnamese diacritics for accent-insensitive queries."""
    import unicodedata
    lowered = (text or "").lower().replace("đ", "d")
    decomposed = unicodedata.normalize("NFD", lowered)
    return "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")


def _is_skipped(relative: str) -> bool:
    for part in _SKIP_PARTS:
        if relative == part or relative.startswith(part + "/") or f"/{part}/" in relative:
            return True
    return False


def _iter_files(root: Path) -> Iterable[Path]:
    seen: set[Path] = set()
    for pattern in _INDEX_PATTERNS:
        for path in root.glob(pattern):
            if not path.is_file() or path in seen:
                continue
            relative = path.relative_to(root).as_posix()
            if _is_skipped(relative):
                continue
            if _SKIP_FILE.search(relative):
                continue
            if path.stat().st_size > 2_000_000:
                continue
            seen.add(path)
            yield path


def _read_text(path: Path) -> str:
    for encoding in ("utf-8", "utf-8-sig", "cp1258", "latin-1"):
        try:
            return path.read_text(encoding=encoding)
        except (UnicodeDecodeError, LookupError):
            continue
    return path.read_text(encoding="utf-8", errors="replace")


def _html_to_markdown(raw: str) -> str:
    """Preserve headings so HTML sections are retrievable like markdown."""
    raw = re.sub(r"(?is)<(script|style|noscript)\b.*?</\1>", " ", raw)

    def heading(match: re.Match) -> str:
        level = int(match.group(1))
        inner = re.sub(r"(?s)<[^>]+>", " ", match.group(2))
        text = re.sub(r"\s+", " ", html.unescape(inner)).strip()
        return f"\n{'#' * level} {text}\n" if text else "\n"

    raw = re.sub(r"(?is)<h([1-6])[^>]*>(.*?)</h\1>", heading, raw)
    raw = re.sub(r"(?is)<li[^>]*>", "\n- ", raw)
    raw = re.sub(r"(?is)<(?:td|th)[^>]*>", " | ", raw)
    raw = re.sub(r"(?is)<br\s*/?>", "\n", raw)
    raw = re.sub(r"(?is)</(?:p|div|section|article|li|h[1-6]|tr|pre|table)>", "\n", raw)
    raw = re.sub(r"(?s)<[^>]+>", " ", raw)
    raw = html.unescape(raw)
    raw = re.sub(r"[ \t]+", " ", raw)
    raw = re.sub(r"\n\s*\n+", "\n\n", raw)
    return raw.strip()


def _chunk_text(text: str, target: int = 950, overlap: int = 140) -> list[Chunk]:
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks: list[Chunk] = []
    buffer: list[str] = []
    size = 0
    line_cursor = 1
    start_line = 1
    for paragraph in paragraphs:
        paragraph = re.sub(r"\s+", " ", paragraph).strip()
        if not paragraph:
            continue
        if size and size + len(paragraph) > target:
            body = "\n".join(buffer).strip()
            if body:
                chunks.append(Chunk("", start_line, line_cursor - 1, body))
            tail = body[-overlap:] if overlap and len(body) > overlap else ""
            buffer = [tail, paragraph] if tail else [paragraph]
            size = sum(len(x) for x in buffer)
            start_line = max(1, line_cursor - tail.count("\n"))
        else:
            buffer.append(paragraph)
            size += len(paragraph)
        line_cursor += 1
    if buffer:
        body = "\n".join(buffer).strip()
        if body:
            chunks.append(Chunk("", start_line, line_cursor, body))
    return chunks


def _chunk_markdown(text: str) -> list[Chunk]:
    chunks: list[Chunk] = []
    heading_stack: list[str] = []
    buffer: list[str] = []
    buffer_start = 1
    line_no = 0
    for raw_line in text.splitlines():
        line_no += 1
        heading_match = re.match(r"^(#{1,6})\s+(.*)$", raw_line)
        if heading_match:
            if buffer:
                body = "\n".join(buffer).strip()
                if body:
                    chunks.append(Chunk(" > ".join(heading_stack), buffer_start, line_no - 1, body))
                buffer = []
            level = len(heading_match.group(1))
            heading_stack = heading_stack[:level - 1] + [heading_match.group(2).strip()]
            buffer_start = line_no
            buffer.append(raw_line)
        else:
            if not buffer:
                buffer_start = line_no
            buffer.append(raw_line)
        if len("\n".join(buffer)) > 1300 and len(buffer) > 2:
            # Carry whole lines instead of a character tail: a tail can start
            # mid-word ("…Đây" → "y là…") and later be quoted as an answer.
            carry = buffer[-2:]
            body = "\n".join(buffer[:-2]).strip()
            if body:
                chunks.append(Chunk(" > ".join(heading_stack), buffer_start, line_no - 2, body))
            buffer = list(carry)
            buffer_start = max(1, line_no - len(carry) + 1)
    if buffer:
        body = "\n".join(buffer).strip()
        if body:
            chunks.append(Chunk(" > ".join(heading_stack), buffer_start, line_no, body))
    return [c for c in chunks if c.text.strip()]


def _chunk_code(text: str, lines_per_chunk: int = 40, overlap: int = 6) -> list[Chunk]:
    lines = text.splitlines()
    chunks: list[Chunk] = []
    step = max(1, lines_per_chunk - overlap)
    for start in range(0, len(lines), step):
        window = lines[start:start + lines_per_chunk]
        if not window:
            break
        body = "\n".join(window).strip()
        if len(body) < 40:
            continue
        heading = ""
        for line in window:
            match = re.match(r"\s*(?:def|class|async def|function|public|private|protected|internal|export)\b[^\n]*", line)
            if match:
                heading = match.group(0).strip()[:120]
                break
        chunks.append(Chunk(heading, start + 1, min(len(lines), start + lines_per_chunk), body))
        if start + lines_per_chunk >= len(lines):
            break
    return chunks


def _chunks_for(path: Path, raw: str) -> list[Chunk]:
    suffix = path.suffix.lower()
    if suffix == ".html":
        # Converted line numbers do not map back to the HTML file, so citations
        # rely on the section heading instead.
        return [Chunk(c.heading, 0, 0, c.text)
                for c in _chunk_markdown(_html_to_markdown(raw))]
    if suffix == ".md":
        return _chunk_markdown(raw)
    if suffix in {".py", ".js", ".css", ".cs", ".csproj"}:
        return _chunk_code(raw)
    return _chunk_text(raw)


def _doc_id(relative: str) -> str:
    return hashlib.sha1(relative.encode("utf-8")).hexdigest()[:16]


def _title_for(path: Path, raw: str) -> str:
    if path.suffix.lower() == ".md":
        match = re.search(r"^#\s+(.+)$", raw, re.MULTILINE)
        if match:
            return match.group(1).strip()
    if path.suffix.lower() == ".html":
        match = re.search(r"(?is)<title>(.*?)</title>", raw)
        if match:
            return html.unescape(match.group(1)).strip()
    return path.stem.replace("_", " ").replace("-", " ")


def build_index(force: bool = False, verbose: bool = False) -> dict:
    root = _repo_root()
    started = time.monotonic()
    inserted_docs = inserted_chunks = skipped = removed = 0
    seen_paths: set[str] = set()
    with _connect() as conn:
        for path in sorted(_iter_files(root)):
            relative = path.relative_to(root).as_posix()
            seen_paths.add(relative)
            try:
                stat = path.stat()
                raw = _read_text(path)
            except OSError:
                continue
            digest = hashlib.sha256(raw.encode("utf-8", errors="replace")).hexdigest()
            existing = conn.execute(
                "SELECT doc_id, sha256, chunks FROM rag_documents WHERE path=?", (relative,)
            ).fetchone()
            if existing and existing["sha256"] == digest and not force:
                skipped += 1
                continue
            doc_id = existing["doc_id"] if existing else _doc_id(relative)
            chunks = _chunks_for(path, raw)
            if existing:
                old_ids = [row[0] for row in conn.execute(
                    "SELECT id FROM rag_chunks WHERE doc_id=?", (doc_id,)).fetchall()]
                for chunk_id in old_ids:
                    conn.execute("DELETE FROM rag_fts WHERE rowid=?", (chunk_id,))
                conn.execute("DELETE FROM rag_chunks WHERE doc_id=?", (doc_id,))
                conn.execute("DELETE FROM rag_documents WHERE doc_id=?", (doc_id,))
            conn.execute(
                "INSERT INTO rag_documents(doc_id,path,title,kind,sha256,size,mtime,chunks) VALUES(?,?,?,?,?,?,?,?)",
                (doc_id, relative, _title_for(path, raw), _KIND_BY_SUFFIX.get(path.suffix.lower(), "text"),
                 digest, stat.st_size, stat.st_mtime, len(chunks)),
            )
            for ordinal, chunk in enumerate(chunks):
                cursor = conn.execute(
                    "INSERT INTO rag_chunks(doc_id,ordinal,heading,start_line,end_line,text) VALUES(?,?,?,?,?,?)",
                    (doc_id, ordinal, chunk.heading, chunk.start_line, chunk.end_line, chunk.text),
                )
                conn.execute(
                    "INSERT INTO rag_fts(rowid,text,heading,text_norm,heading_norm) VALUES(?,?,?,?,?)",
                    (cursor.lastrowid, chunk.text, chunk.heading,
                     _strip_diacritics(chunk.text), _strip_diacritics(chunk.heading)),
                )
                inserted_chunks += 1
            inserted_docs += 1
        stale = conn.execute("SELECT doc_id, path FROM rag_documents").fetchall()
        for row in stale:
            if row["path"] not in seen_paths:
                old_ids = [r[0] for r in conn.execute(
                    "SELECT id FROM rag_chunks WHERE doc_id=?", (row["doc_id"],)).fetchall()]
                for chunk_id in old_ids:
                    conn.execute("DELETE FROM rag_fts WHERE rowid=?", (chunk_id,))
                conn.execute("DELETE FROM rag_chunks WHERE doc_id=?", (row["doc_id"],))
                conn.execute("DELETE FROM rag_documents WHERE doc_id=?", (row["doc_id"],))
                removed += 1
        conn.execute("INSERT INTO rag_meta(key,value) VALUES('built_at',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                     (time.strftime("%Y-%m-%dT%H:%M:%S"),))
        conn.execute("INSERT INTO rag_meta(key,value) VALUES('schema',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                     (_SCHEMA_VERSION,))
        conn.commit()
    elapsed = round(time.monotonic() - started, 2)
    if verbose:
        print(f"index: {inserted_docs} docs updated, {inserted_chunks} chunks, "
              f"{skipped} unchanged, {removed} removed, {elapsed}s")
    status = index_status()
    status["elapsed_s"] = elapsed
    return status


# Multi-word concepts are kept as one retrieval term so a query is not diluted
# into syllables ("kiến"/"trúc") that match unrelated text.
_PHRASES = [
    "kiến trúc", "trí nhớ", "cấu hình", "cơ sở dữ liệu", "mô hình", "huấn luyện",
    "đánh giá", "nhà cung cấp", "ngôn ngữ", "quyết định", "dự án", "thành phần",
    "hệ thống", "bảo mật", "kiểm thử", "tài liệu", "giao diện", "người dùng",
    "dữ liệu", "hướng dẫn", "phiên làm việc", "báo cáo", "tính năng", "tầng", "cổng",
    "mật khẩu",
]

# Cross-language aliases let a Vietnamese question match English headings and
# an English question match Vietnamese prose, without a translation model.
_PHRASE_ALIASES = {
    "kiến trúc": ["architecture"],
    "trí nhớ": ["memory"],
    "cấu hình": ["config", "configuration"],
    "cơ sở dữ liệu": ["database", "sqlite"],
    "mô hình": ["model"],
    "huấn luyện": ["training", "train"],
    "đánh giá": ["evaluation", "evaluate"],
    "nhà cung cấp": ["provider"],
    "ngôn ngữ": ["language"],
    "quyết định": ["decision"],
    "dự án": ["project"],
    "thành phần": ["component"],
    "hệ thống": ["system"],
    "bảo mật": ["security"],
    "kiểm thử": ["test", "testing"],
    "tài liệu": ["documentation", "docs"],
    "giao diện": ["ui", "interface"],
    "người dùng": ["user"],
    "dữ liệu": ["data"],
    "hướng dẫn": ["guide", "runbook"],
    "phiên làm việc": ["session"],
    "báo cáo": ["report"],
    "tính năng": ["feature", "capability"],
    "tầng": ["layer", "component"],
    "cổng": ["gateway"],
    "mật khẩu": ["password"],
    # "Provider sập" is the operator's wording for a provider outage; the docs
    # describe the same event as "mất kết nối" / "lỗi" / "fail".
    "sập": ["lỗi", "mất kết nối", "down", "fail", "crash"],
}

# The product name is a namespace, not a content requirement: a chunk titled
# "3.10 Gateway" is already about DUSN-X even if the name is not repeated.
_ANCHOR_TERMS = {"dusn", "dusnx", "dusn-x", "dusn_x", "chatbot"}


def _phrase_terms(query: str) -> list[str]:
    """Detect concepts in the query with or without Vietnamese diacritics."""
    normalized = (query or "").lower()
    folded = _strip_diacritics(normalized)
    return [phrase for phrase in _PHRASES
            if phrase in normalized or _strip_diacritics(phrase) in folded]


def _alternatives(term: str) -> list[str]:
    values = [term]
    for alias in _PHRASE_ALIASES.get(term, []):
        if alias not in values:
            values.append(alias)
    return values


def _terms(query: str) -> list[str]:
    normalized = (query or "").lower()
    terms: list[str] = [phrase for phrase in _phrase_terms(query)]
    phrases = list(terms)
    phrase_syllables = {form for phrase in phrases for word in phrase.split()
                        for form in (word, _strip_diacritics(word))}
    tokens = re.findall(r"[0-9a-zà-ỹđ_][0-9a-zà-ỹđ_.\-]*", normalized, re.UNICODE)

    def keep(token: str) -> bool:
        return (len(token) >= 2 and token not in _STOPWORDS
                and _strip_diacritics(token) not in _STOPWORDS)

    for token in tokens:
        token = token.strip(".-_")
        if not keep(token):
            continue
        # A syllable already represented by a multi-word concept adds noise.
        if token in phrase_syllables:
            continue
        parts = [part for part in re.split(r"[_.\-/]", token) if keep(part)]
        for part in parts or [token]:
            if part not in terms:
                terms.append(part)
            # Split camelCase/snake_case identifiers, but never Vietnamese words:
            # the accent-aware regex above keeps them whole.
            if re.fullmatch(r"[A-Za-z0-9]+", part):
                for piece in re.findall(r"[A-Z]?[a-z]+|[A-Z]+(?![a-z])|\d+", part):
                    piece = piece.lower()
                    if keep(piece) and piece not in terms:
                        terms.append(piece)
    return terms


def _fts_query(terms: list[str]) -> Optional[str]:
    fts_terms = [t for t in terms if len(t) >= 3]
    if not fts_terms:
        return None
    quoted = []
    seen: set[str] = set()
    for term in fts_terms[:16]:
        safe = re.sub(r'["*^:()\-]', " ", term).strip()
        if len(safe) >= 3 and safe not in seen:
            quoted.append(f'"{safe}"')
            seen.add(safe)
    return " OR ".join(quoted) if quoted else None


# Only queries that plausibly target this repository or its stack get local
# evidence injected. Hints are written without diacritics because the query is
# folded before matching (see should_retrieve), so "kien truc" and "kiến trúc"
# take the same path. Generic language names ("python", "javascript") are not
# enough: the corpus has no tutorial material, so retrieving would only add
# unrelated snippets to a general-knowledge answer.
_RETRIEVAL_HINTS = [
    "dusn", "repo", "repository", "codebase", "ma nguon", "source code",
    "project", "du an", "tai lieu", "documentation", "docs", "readme",
    "handoff", "runbook", "kien truc", "architecture", "gateway", "fastapi",
    "ai api", "endpoint", "router", "checkpoint", "provider", "ollama",
    "openai", "memory", "tri nho", "sqlite", "rag", "retrieval", "embedding",
    "sft", "gguf", "lora", "dataset", "training", "huan luyen",
    "word add-in", "word-addin", "word addin", "office.js", "powerpoint",
    "office", "add-in", "addin", "web ui", "frontend", "backend",
    "danh gia", "evaluation", "benchmark", "quality gate", "cau hinh",
    "config", "requirements", "docker", "compose", "uvicorn", "auth",
    "token", "session", "phien", "password", "mat khau", "hash", "scrypt",
    "ma hoa", "encrypt", "layer", "chuc nang", "hoat dong", "he thong",
    "timeout", "port", "database", "du lieu", "luu tru", "su kien", "error",
    "fallback", "log", "quyet dinh", "decision", "de xuat", "proposal",
    "job", "slide", "api", "llm", "prompt", "temperature", "context",
    "kiem thu", "pytest", "dotnet", "asp.net", "github actions", "workflow",
    "quy trinh", "luong", "tin nhan", "model", "mo hinh", "chinh sach",
    "security", "bao mat", "permission", "van hanh", "deploy",
    "trien khai", "gioi han", "ngon ngu", "cli",
    # Local startup questions ("web chạy local thế nào?") name the runbook
    # topic without using the word "runbook".
    "chay local", "chay web", "chay du an", "localhost", "start-local",
    "khoi dong", "cai dat",
]
_RETRIEVAL_HINT = re.compile(
    r"\b(?:" + "|".join(re.escape(hint) for hint in _RETRIEVAL_HINTS) + r")\b")
# Code identifiers ("answer_from_hits", "ChatResponse") name repository
# symbols even when no prose hint appears in the question.
_IDENTIFIER_HINT = re.compile(r"[a-z][a-z0-9]*(?:_[a-z0-9]+)+|[A-Z][a-z0-9]+[A-Z]")


def should_retrieve(query: str) -> bool:
    """Cheap gate: could the local corpus contain an answer to this question?

    The corpus documents DUSN-X and its stack, not general knowledge, so a
    vocabulary hint or a code identifier is required. Without this gate a
    question like "thời tiết hôm nay" matches ordinary words in status
    reports and would inject unrelated passages into the answer.
    """
    if not query or len(query.strip()) < 3:
        return False
    folded = _strip_diacritics(query.lower())
    return bool(_RETRIEVAL_HINT.search(folded) or _IDENTIFIER_HINT.search(query))


def has_evidence(hits: list[Hit], min_score: float = 55.0) -> bool:
    """Whether retrieval found at least one passage relevant enough to cite."""
    return bool(hits) and hits[0].score >= min_score and hits[0].coverage >= 0.34


def has_strong_evidence(hits: list[Hit], min_score: float = 70.0) -> bool:
    """Stricter gate used before injecting context into general answers."""
    return bool(hits) and hits[0].score >= min_score and hits[0].coverage >= 0.5


def _path_weight(path: str) -> float:
    """Prefer canonical docs over historical review/evidence tables."""
    p = path.replace("\\", "/")
    lower = p.lower()
    if "/evidence/" in lower or lower.startswith("docs/evidence/"):
        return -25.0
    if "review_table" in lower or lower.endswith("manifest.md"):
        return -6.0
    if p == "docs/ARCHITECTURE.md":
        return 14.0
    if p == "README.md":
        return 8.0
    if p.startswith("docs/reports/") and p.endswith(".html"):
        return 5.0
    if p.startswith("docs/") and p.endswith(".md"):
        if re.search(r"week\d+_acceptance|handover_verification|release_verification|"
                     r"train_readiness|project_status", lower):
            # Verification/status tables repeat feature names inside test rows;
            # quoting a row is not an explanation.
            return -14.0
        return 4.0
    if p.startswith("scripts/"):
        return -12.0
    if re.search(r"designed_data|synthetic|benchmark", lower):
        # Generated scenario literals repeat product terms without documenting
        # the product; quoting them produces nonsense answers.
        return -20.0
    if p.startswith(("word-addin/", "powerpoint-addin/", "gateway-dotnet/", "web-ui/")) \
            or p.endswith((".py", ".js", ".cs")):
        return -5.0
    return 0.0


_DEFINITION_QUERY = re.compile(
    r"(?i)(?:\blà gì\b|\bwhat is\b|\bwhat's\b|\bgiới thiệu\b|\btổng quan\b|\boverview\b|\bdefine\b)")


def _query_identifier(query: str) -> Optional[str]:
    """The repository symbol a question names, if any ("answer_from_hits")."""
    return next(
        (token for token in re.findall(r"[A-Za-z_][A-Za-z0-9_]{2,}", query)
         if "_" in token or re.search(r"[a-z][A-Z]", token)), None)


def _definition_hit(identifier: str) -> Optional[Hit]:
    """Fetch the chunk holding ``def/class <identifier>`` directly.

    FTS scoring ranks chunks by how often the words occur, so the declaration
    itself can fall outside the candidate window. A definition query needs the
    declaration, not its mentions.
    """
    if not is_available():
        return None
    with _connect() as conn:
        row = conn.execute(
            """SELECT c.heading, c.start_line, c.end_line, c.text, d.path, d.title
               FROM rag_chunks c JOIN rag_documents d ON d.doc_id = c.doc_id
               WHERE c.text LIKE ? OR c.text LIKE ?
               ORDER BY length(c.text) LIMIT 1""",
            (f"%def {identifier}%", f"%class {identifier}%"),
        ).fetchone()
    if not row:
        return None
    return Hit(row["path"], row["title"] or "", row["heading"] or "",
               row["start_line"] or 0, row["end_line"] or 0, row["text"],
               240.0, 0.0, coverage=1.0)


def retrieve(query: str, top_k: int = 5, max_chars: int = 4200) -> list[Hit]:
    if not is_available():
        return []
    terms = _terms(query)
    if not terms:
        return []
    # The product name stays in the FTS expansion (it narrows candidates) but is
    # not required for coverage: canonical sections often use only the feature
    # name ("3.10 Gateway") without repeating "DUSN-X".
    content_terms = [term for term in terms if term not in _ANCHOR_TERMS] or terms
    definition_query = bool(_DEFINITION_QUERY.search(query or ""))
    expanded: list[str] = []
    # Prefer content terms: adding the product anchor to an OR query pushes
    # feature sections ("3.10 Gateway") out of the bm25 candidate window.
    for term in content_terms:
        for variant in _alternatives(term):
            expanded.append(variant)
            folded = _strip_diacritics(variant)
            if folded != variant and len(folded) >= 3:
                expanded.append(folded)
        folded = _strip_diacritics(term)
        if folded != term and len(folded) >= 3:
            expanded.append(folded)
    match = _fts_query(expanded)
    if not match:
        return []
    phrase = re.sub(r"\s+", " ", (query or "").lower()).strip()
    with _connect() as conn:
        rows = conn.execute(
            """SELECT c.id, c.heading, c.start_line, c.end_line, c.text,
                      d.path, d.title, bm25(rag_fts) AS rank
               FROM rag_fts JOIN rag_chunks c ON c.id = rag_fts.rowid
               JOIN rag_documents d ON d.doc_id = c.doc_id
               WHERE rag_fts MATCH ? ORDER BY rank LIMIT 60""",
            (match,),
        ).fetchall()
    hits: list[Hit] = []

    def present(term: str, value: str, folded_value: str) -> bool:
        return any(alt in value or _strip_diacritics(alt) in folded_value
                   for alt in _alternatives(term))

    for row in rows:
        text = row["text"] or ""
        heading_text = (row["heading"] or "").lower()
        title_text = (row["title"] or "").lower()
        haystack = f"{heading_text} {text}".lower()
        folded_haystack = _strip_diacritics(haystack)

        matched = [term for term in content_terms if present(term, haystack, folded_haystack)]
        coverage = len(matched) / max(1, len(content_terms))
        exact = 1.0 if len(phrase) >= 4 and phrase in haystack else 0.0
        if len(content_terms) <= 2:
            qualifies = len(matched) >= len(content_terms)
        elif len(content_terms) == 3:
            qualifies = len(matched) >= 2
        else:
            qualifies = coverage >= 0.5 and len(matched) >= 2
        if exact:
            qualifies = True
        if not qualifies:
            continue
        folded_title = _strip_diacritics(title_text)
        heading_parts = [part for part in heading_text.split(" > ") if part.strip()]
        heading_tail = heading_parts[-1] if heading_parts else ""
        parent_heading = heading_parts[-2] if len(heading_parts) > 1 else (heading_parts[0] if heading_parts else "")
        top_heading = heading_parts[1] if len(heading_parts) > 2 else ""
        folded_tail = _strip_diacritics(heading_tail)
        folded_parent = _strip_diacritics(parent_heading)
        folded_top = _strip_diacritics(top_heading)
        heading_matches = sum(1 for term in matched
                              if term in heading_tail or _strip_diacritics(term) in folded_tail)
        cleaned_tail = re.sub(r"^[\s\d.,)\-–]+", "", heading_tail).strip()
        folded_cleaned_tail = _strip_diacritics(cleaned_tail)
        dedicated_matches = sum(1 for term in matched
                                if cleaned_tail.startswith(term)
                                or folded_cleaned_tail.startswith(_strip_diacritics(term)))
        section_matches = sum(1 for term in matched
                              if term in parent_heading or _strip_diacritics(term) in folded_parent)
        top_matches = sum(1 for term in matched
                          if top_heading and (term in top_heading or _strip_diacritics(term) in folded_top))
        title_matches = sum(1 for term in matched
                            if term in title_text or _strip_diacritics(term) in folded_title)
        term_frequency = sum(min(4, haystack.count(term)) for term in matched)
        rank = float(row["rank"] or 0.0)
        score = (coverage * 100 + exact * 25
                 + heading_matches * 14 + section_matches * 14 + top_matches * 6
                 + dedicated_matches * 18 + title_matches * 3
                 + min(10, term_frequency)
                 + min(10.0, max(0.0, -rank)) + _path_weight(row["path"]))
        if definition_query and _DEFINITION_QUERY.search(heading_tail):
            score += 20
        if definition_query and (row["start_line"] or 0) == 1:
            score += 8
        # Unimplemented/limitation sections match product terms but rarely answer
        # a "how does it work" question; demote unless the ask is about them.
        if re.search(r"(?:mo rong|phase 2|rui ro|gioi han|chua trien khai)", folded_tail) \
                and not re.search(r"(?:mo rong|phase 2|rui ro|gioi han|chua)",
                                  _strip_diacritics(query.lower())):
            score -= 45.0
        hits.append(Hit(row["path"], row["title"] or "", row["heading"] or "",
                        row["start_line"] or 0, row["end_line"] or 0, text,
                        score, rank, coverage=coverage))
    hits.sort(key=lambda h: h.score, reverse=True)
    selected: list[Hit] = []
    per_doc_selected: dict[str, int] = {}
    for hit in hits:
        if len(selected) >= top_k:
            break
        if per_doc_selected.get(hit.path, 0) >= 2:
            continue
        selected.append(hit)
        per_doc_selected[hit.path] = per_doc_selected.get(hit.path, 0) + 1
    identifier = _query_identifier(query)
    if identifier:
        definition = _definition_hit(identifier)
        if definition:
            selected = [definition] + [
                hit for hit in selected
                if (hit.path, hit.start_line) != (definition.path, definition.start_line)
            ]
            selected = selected[:top_k]
    return selected


def build_context(hits: list[Hit], language: str = "vi", max_chars: int = 3600) -> str:
    if not hits:
        return ""
    header = ("Tài liệu tham khảo từ repository (chỉ dùng thông tin trong đây; "
              "trích dẫn nguồn bằng [S1], [S2]... tương ứng):"
              if language != "en" else
              "Repository reference material (use only the information below; "
              "cite sources as [S1], [S2]...):")
    lines = [header]
    used = 0
    for index, hit in enumerate(hits, 1):
        hit.source_id = f"S{index}"
        label = f"[S{index}] {hit.path}"
        if hit.heading:
            label += f" — {hit.heading}"
        if hit.start_line:
            label += f" (lines {hit.start_line}-{hit.end_line})"
        budget = min(1100, max_chars - used)
        if budget < 120:
            break
        body = hit.text[:budget]
        lines.append(label)
        lines.append(body)
        used += len(label) + len(body)
    return "\n\n".join(lines)


def build_context_en(hits: list[Hit]) -> str:
    return build_context(hits, "en")


# ── Extractive answers ────────────────────────────────────────────────────────
# A 1.5B local model can ignore supplied context and invent product facts.
# For questions the index can answer directly, sentences are quoted from the
# retrieved passages and cited, so the answer cannot drift from the source.

_VI_CHARS = re.compile(
    r"[ăâđêôơưàáảãạằắẳẵặầấẩẫậèéẻẽẹềếểễệìíỉĩịòóỏõọồốổỗộờớởỡợùúủũụừứửữựỳýỷỹỵ]",
    re.IGNORECASE,
)
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[\"'(\[A-ZÀ-Ỹ0-9])")
_SECTION_NUMBER = re.compile(r"^\d+(?:\.\d+)*[.)]?\s+")
# Subheadings such as "Cấu hình sinh" or "Tổng quan" carry no topic of their
# own; their parent section does ("3.7 Provider: timeout, sinh, ...").
_DETAIL_HEADING = re.compile(
    r"^(?:cấu hình|tổng quan|chi tiết|ghi chú|ví dụ|kết quả|định nghĩa|"
    r"luồng|hiện trạng|mô tả|tham số|biến môi trường|configuration|overview|"
    r"details|notes|example|result|definition|flow|status)\b", re.IGNORECASE)
# Source chunks are documentation only in the sense that they are indexed;
# quoting a function body as an answer is never correct.
_CODE_LIKE = re.compile(
    r"^\s*(?:def |class |async def |if |elif |else\b|for |while |return |import |from |@)"
    r"|\bself\.|\bos\.getenv\(|=\s*\{|\}\s*$|->\s*[A-Za-z_]+:")
_CODE_SUFFIXES = (".py", ".js", ".cs", ".ts")
# Statements flattened out of a code chunk. They mention the symbol but never
# explain it; the docstring path answers identifier questions instead.
_STATEMENT = re.compile(
    r"(?:^|\s)\w+\s*=\s*|\)\s*->\s*|\b(?:None|True|False)\b|\bself\b|\bprint\(")
# Collection literals copied out of a test table or config list: they contain
# the query words but never explain them.
_LITERAL = re.compile(r"^[\(\[\{]\s*[\"']")
# Code punctuation that prose never uses. A chunk cut mid-object can start with
# an identifier ("rag_used: response.rag_used, ...") and slip past _CODE_LIKE.
_CODE_NOISE = re.compile(r"[{};]|=>|\bconsole\.|\bresponse\.|::")
# Rows copied from evaluation and training tables: their words are file names,
# scenario ids, and verdicts, never a description of the product.
_SCENARIO_ROW = re.compile(
    r"\bCASE_[A-Z0-9_]+\b|—\s*(?:PASSED|FAILED|pass|fail)\s*—|"
    r"\bprovider=ollama,\s*source=|\b[a-z][a-z0-9_]{4,}:\s+[\w ]+\s+->\s+\w"
    # Evaluation rows often restate the question verbatim, so they match every
    # query word while answering nothing ("Q6 — mật khẩu ... — vi — 61").
    r"|(?:^|\s)Q\d+\s*—")
# Words that frame a question ("câu hỏi", "hệ thống", "tính năng") and occur in
# almost every document. A passage that shares only these says nothing about
# the topic being asked, so it must not be quoted as an answer.
_GENERIC_QUERY_TERMS = {
    "cau", "hoi", "dang", "he thong", "tinh nang", "chuc nang", "kha nang",
    "cach", "nao", "gi", "the nao", "nhu the nao", "lam sao",
}
# Status and verification reports record work done ("Bổ sung ... vào ..."),
# not what the product does; those entries are history, not description.
_STATUS_DOC = re.compile(
    r"(?:week\d+|handover|release_verification|train_readiness|project_status|"
    r"phase\d+_\w*update|_acceptance|_pilot|_training)", re.IGNORECASE)
_CHANGE_ENTRY = re.compile(
    r"^(?:bổ sung|bo sung|thêm|them|sửa|sua|khắc phục|khac phuc|cập nhật|cap nhat|"
    r"nâng cấp|nang cap|triển khai|trien khai|đã\s+\w+|added|fixed|updated|removed)\b",
    re.IGNORECASE)
# "Tuần 4 bổ sung ..." opens a work log, wherever the note was filed.
_WEEK_ENTRY = re.compile(r"^(?:tuần|tuan|week|phase)\s*\d+", re.IGNORECASE)


def _plain_blocks(text: str) -> list[tuple[str, bool]]:
    """Cleaned paragraphs as (text, is_heading) without markdown/code/table noise.

    Wrapped markdown lines are joined so a sentence is never quoted from its
    middle; blank lines, headings and code fences start a new block.
    """
    blocks: list[tuple[str, bool]] = []
    buffer: list[str] = []
    last_was_table_row = False

    def flush() -> None:
        nonlocal last_was_table_row
        if buffer:
            blocks.append((" ".join(buffer), False))
            buffer.clear()
        last_was_table_row = False

    in_code = False
    for raw in (text or "").splitlines():
        line = raw.strip()
        if line.startswith("```"):
            in_code = not in_code
            flush()
            continue
        if in_code:
            continue
        if line.startswith("|"):
            previous_was_table_row = last_was_table_row
            flush()
            cells = [cell.strip() for cell in line.strip("|").split("|")]
            if all(not cell or re.fullmatch(r":?-{3,}:?", cell) for cell in cells):
                # The row before the separator is a column-header strip, not a
                # sentence: quoting "Mã ca — Loại ca — Prompt" answers nothing.
                if previous_was_table_row and blocks:
                    blocks.pop()
                continue
            readable = " — ".join(cell for cell in cells if cell)
            if readable:
                blocks.append((readable, False))
                last_was_table_row = True
            continue
        if not line or re.fullmatch(r"[-=_*]{3,}", line):
            flush()
            continue
        # Each markdown list item is its own answer-sized block; joining a whole
        # bullet list into one paragraph makes every bullet compete as a sentence.
        if re.match(r"^(?:[-*+]|\d+[.)])\s+", line):
            flush()
        heading = bool(re.match(r"^#{1,6}\s+", line))
        line = re.sub(r"^#{1,6}\s*", "", line)
        line = re.sub(r"^(?:[-*+]|\d+[.)])\s+", "", line)
        line = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", line)
        line = line.replace("**", "").replace("__", "").replace("`", "")
        if not line:
            continue
        if heading:
            flush()
            blocks.append((line, True))
        else:
            buffer.append(line)
    flush()
    return blocks


def _split_sentences(text: str) -> list[str]:
    parts = _SENTENCE_SPLIT.split(text)
    if len(parts) <= 1:
        # Never split on ';': semicolons usually separate items inside one
        # claim (a layer list, a config list), and cutting there truncates it.
        parts = re.split(r"(?<=[.!?])\s+", text)
    return [part.strip() for part in parts if part.strip()]


def _truncate(text: str, limit: int = 460) -> str:
    if len(text) <= limit:
        return text
    cut = text[:limit]
    for mark in (". ", "; ", ", "):
        point = cut.rfind(mark)
        if point >= limit * 0.55:
            return cut[:point + 1].rstrip() if mark == ". " else cut[:point].rstrip(",;: ") + "…"
    return cut.rsplit(" ", 1)[0].rstrip(",;:") + "…"


def _definition_answer(identifier: str, hits: list[Hit]) -> Optional[str]:
    """Quote a declaration and its docstring for a code-identifier question.

    "What does X return?" cannot be answered by arbitrary statements that
    mention X; the declaration plus docstring is the authoritative passage.
    """
    pattern = re.compile(
        rf"(?m)^\s*(?P<sig>(?:async\s+)?(?:def|class)\s+{re.escape(identifier)}\b"
        rf"[\s\S]{{0,300}}?:[ \t]*\n)(?P<body>[\s\S]{{0,1600}})")
    for rank, hit in enumerate(hits[:3], 1):
        match = pattern.search(hit.text)
        if not match:
            continue
        signature = re.sub(r"\s+", " ", match.group("sig")).strip()
        body = match.group("body")
        doc = re.search(r'(?:"""|\'\'\')(.*?)(?:"""|\'\'\')', body, re.S)
        if doc:
            text = re.sub(r"\s+", " ", doc.group(1)).strip()
        else:
            comment = re.search(r"(?m)^\s*#\s*(.{24,}?)\s*$", body)
            if not comment:
                continue
            text = comment.group(1)
        text = _truncate(text, 520)
        quote = f"{signature} {text}"
        header = ("Theo tài liệu nội bộ của DUSN-X:" if _VI_CHARS.search(quote)
                  else "From the DUSN-X internal documentation:")
        return f"{header}\n- {quote} [S{rank}]"
    return None


def answer_from_hits(query: str, hits: list[Hit], language: str = "vi",
                     max_sentences: int = 3) -> Optional[str]:
    """Return a cited, source-faithful answer built from retrieved sentences.

    The output quotes the documentation instead of paraphrasing it, so every
    factual claim maps to a citation. Returns None when no passage is relevant
    enough, in which case the caller falls back to normal generation.
    """
    if not hits:
        return None
    terms = [term for term in _terms(query) if term not in _ANCHOR_TERMS] or _terms(query)
    if not terms:
        return None

    identifier = next(
        (token for token in re.findall(r"[A-Za-z_][A-Za-z0-9_]{2,}", query)
         if "_" in token or re.search(r"[a-z][A-Z]", token)), None)
    if identifier:
        definition = _definition_answer(identifier, hits)
        if definition:
            return definition

    def term_in(term: str, folded: str, raw: str = "") -> bool:
        for alt in _alternatives(term):
            needle = _strip_diacritics(alt)
            if _VI_CHARS.search(alt) and raw:
                # Diacritics are part of the word: "lõi" (core) is not "lời"
                # (word), although both fold to "loi". Accented queries match
                # accented text on a word edge.
                if re.search(rf"(?<![^\W_]){re.escape(alt)}(?![^\W_])", raw):
                    return True
            elif len(needle) <= 3:
                if re.search(rf"(?<![a-z0-9]){re.escape(needle)}(?![a-z0-9])", folded):
                    return True
            elif needle in folded:
                return True
        return False

    def section_heading(hit: Hit) -> str:
        # The first segment is the document title; it names the product, not
        # the section, so it must not make every chunk look relevant.
        parts = [part.strip() for part in (hit.heading or "").split(">") if part.strip()]
        return " > ".join(parts[1:] or parts)

    def is_table_header(sentence: str) -> bool:
        cells = [cell.strip() for cell in sentence.split(" — ")]
        return len(cells) >= 3 and all(len(cell.split()) <= 6 for cell in cells)

    # A section heading that covers at least half the query (and two terms) is
    # about the question even when its bullets repeat no query word, e.g.
    # "3.7 Provider ... > Cấu hình sinh" answers "cấu hình Ollama provider".
    heading_need = min(len(terms), max(2, (len(terms) + 1) // 2))
    error_like = re.compile(
        r"(?:lỗi|error|failed|failure|thất bại|không khả dụng|unable|crash|sự cố|"
        r"mất kết nối|ngắt kết nối)")
    query_folded = _strip_diacritics(query.lower())
    asks_errors = bool(re.search(
        r"(?:loi|error|fail|that bai|su co|khong kha dung|fallback|sap|"
        r"mat ket noi|crash|down)", query_folded))

    candidates: list[tuple[float, int, int, str, int]] = []
    for rank, hit in enumerate(hits[:3], 1):
        heading_raw = section_heading(hit).lower()
        heading_folded = _strip_diacritics(heading_raw)
        title_folded = _strip_diacritics((hit.title or "").lower()).rstrip(".")
        heading_terms = [term for term in terms
                         if term_in(term, heading_folded, heading_raw)]
        # The leaf section must carry part of the question; a parent heading
        # ("3 Thuật toán cốt lõi") alone must not make every child relevant, or
        # an unrelated subsection would answer a "tính năng cốt lõi" question.
        heading_parts = [part.strip() for part in heading_raw.split(">") if part.strip()]
        leaf_raw = heading_parts[-1] if heading_parts else ""
        parent_raw = heading_parts[-2] if len(heading_parts) > 1 else ""
        leaf_terms = [term for term in terms
                      if term_in(term, _strip_diacritics(leaf_raw), leaf_raw)]
        parent_terms = [term for term in terms
                        if term not in leaf_terms
                        and term_in(term, _strip_diacritics(parent_raw), parent_raw)]
        leaf_is_detail = bool(_DETAIL_HEADING.match(_SECTION_NUMBER.sub("", leaf_raw)))
        section_relevant = (len(leaf_terms) >= heading_need
                            or (leaf_is_detail and len(parent_terms) >= heading_need)
                            or (len(leaf_terms) >= 1
                                and len(leaf_terms) + len(parent_terms) >= heading_need))
        negative_section = bool(re.search(
            r"(?:tieu cuc|negative|that bai|su co|failed)", heading_folded))

        def score_text(text: str, matched: list[str], line_index: int, fallback: bool) -> float:
            folded = _strip_diacritics(text.lower())
            if fallback:
                score = 2.0 + len(heading_terms) * 1.5 - (rank - 1) * 4.0
            else:
                score = (len(matched) / max(1, len(terms))) * 10.0 - (rank - 1) * 4.0
                if heading_terms:
                    score += 1.0
                if section_relevant:
                    score += 2.0
            if line_index <= 2:
                score += 1.5
            for term in matched:
                folded_term = re.escape(_strip_diacritics(term))
                if re.search(rf"{folded_term}\s+(?:là|is|are|refers|means|serves|dùng|được dùng)", folded):
                    score += 4.0
            if re.search(r"(?:là|is|are|gồm|bao gồm|consists|dùng để|serves|provides|cung cấp)", folded):
                score += 1.0
            score += min(3, folded.count(",")) * 0.5 if not fallback else 0.0
            if (not fallback and
                    ("→" in text or "->" in text or "bao gồm" in folded or "gồm" in folded)):
                score += 3.0
            if re.search(r"(?:không phải|chưa triển khai|giới hạn|limitation|chưa có)", folded):
                score -= 2.5
            if negative_section and not asks_errors:
                score -= 5.0
            if error_like.search(folded):
                # Failure logs answer "what went wrong", not "how it works";
                # when failure is the question, they are the answer.
                score += 3.0 if asks_errors else -3.0
            if _STATUS_DOC.search(hit.path):
                # Verification logs mix evidence prose into feature names; they
                # are the last place to quote when a canonical doc exists.
                score -= 3.5
            if bool(_VI_CHARS.search(text)) == (language != "en"):
                score += 2.0
            return score

        offset = 0
        for line_index, (line, is_heading) in enumerate(_plain_blocks(hit.text)):
            if is_heading:
                offset += 1
                continue
            block = _SECTION_NUMBER.sub("", line.strip())
            if len(block) < 24:
                offset += 1
                continue
            folded_plain = _strip_diacritics(block.lower()).rstrip(".")
            if folded_plain == title_folded or (
                    heading_folded and folded_plain == heading_folded.split(" > ")[-1].rstrip(".")):
                offset += 1
                continue
            folded = _strip_diacritics(block.lower())
            if re.search(r"(?:mo rong|phase 2|chua trien khai|chua duoc trien khai)", folded) \
                    and not re.search(r"(?:mo rong|phase 2|chua)", query_folded):
                offset += 1
                continue
            if is_table_header(block):
                offset += 1
                continue
            if _SCENARIO_ROW.search(block):
                offset += 1
                continue
            if block.endswith(":") and len(block) > 40:
                # Drop a short list lead-in ("Quy trình:") that only introduces
                # blocks quoted separately.
                head, sep, tail = block.rpartition(". ")
                if sep and len(tail) <= 40:
                    block = head + "."
                    folded = _strip_diacritics(block.lower())
            if _CODE_LIKE.search(block):
                offset += 1
                continue
            if hit.path.lower().endswith(_CODE_SUFFIXES) and (
                    _STATEMENT.search(block) or _LITERAL.match(block)
                    or _CODE_NOISE.search(block)):
                # A code statement is evidence that a symbol exists, not an
                # explanation of it; quoting it answers nothing.
                offset += 1
                continue
            matched = [term for term in terms
                       if term_in(term, folded, block.lower())]
            # Question framing ("câu hỏi", "hệ thống") appears in nearly every
            # document; sharing only those words is not topical overlap.
            specific = [term for term in matched
                        if _strip_diacritics(term) not in _GENERIC_QUERY_TERMS]
            if not specific and not section_relevant:
                offset += 1
                continue
            if ((_STATUS_DOC.search(hit.path) and _CHANGE_ENTRY.match(block))
                    or _WEEK_ENTRY.match(block)):
                offset += 1
                continue
            # A single short, common term ("hỏi") is not evidence that this
            # block answers the question, even near the top of a chunk.
            strong_single = any(len(_strip_diacritics(term)) >= 4 for term in specific)
            # Keep the whole claim when the block is clearly on topic: follow-up
            # sentences often drop the subject ("Nó phục vụ ...") and cutting
            # them loses the actual answer.
            if specific and (len(specific) >= 2 or (strong_single and (line_index <= 2 or len(terms) < 3))):
                text = _truncate(block, 560)
                candidates.append((score_text(text, specific, line_index, False),
                                   rank, offset, text, rank))
                offset += 1
                continue
            if section_relevant:
                # The section is about the question even if this bullet repeats
                # no query word (e.g. "temperature=0.1 ..." under "Cấu hình").
                text = _truncate(block, 560)
                candidates.append((score_text(text, matched, line_index, True),
                                   rank, offset, text, rank))
                offset += 1
                continue
            for sentence in _split_sentences(block):
                sentence = sentence.strip()
                if len(sentence) < 24:
                    continue
                sentence_raw = sentence.lower()
                sentence_any = [term for term in terms
                                if term_in(term, _strip_diacritics(sentence_raw), sentence_raw)]
                if len(terms) >= 3 and len(sentence_any) == 1 \
                        and not re.search(r"(?:là|is|are|gồm|bao gồm|consists|dùng để|serves)",
                                          _strip_diacritics(sentence_raw)):
                    # A single incidental term in a long sentence is not an answer.
                    continue
                sentence_matched = sentence_any
                sentence_specific = [term for term in sentence_matched
                                     if _strip_diacritics(term) not in _GENERIC_QUERY_TERMS]
                if not sentence_specific:
                    continue
                text = _truncate(sentence)
                candidates.append((score_text(text, sentence_specific, line_index, False),
                                   rank, offset, text, rank))
                offset += 1

    if not candidates:
        return None
    candidates.sort(key=lambda item: (-item[0], item[1], item[2]))
    if os.getenv("DUSNX_RAG_DEBUG") == "1":
        for item in candidates[:12]:
            print(f"  cand {item[0]:6.2f} r{item[1]} o{item[2]} :: {item[3][:70]}", file=sys.stderr)
    # Drop weak tail quotes: a bullet is kept when it comes from the same
    # chunk as the best passage (a config list stays together) or when another
    # chunk matches almost as strongly (true corroboration, not a coincidental
    # shared word).
    top_score, top_rank = candidates[0][0], candidates[0][1]
    floor = max(5.0, top_score * 0.6)
    candidates = [item for item in candidates
                  if item[0] >= floor
                  and (item[1] == top_rank or item[0] >= top_score * 0.8)]
    chosen = candidates[:max_sentences]
    # Strongest passage first; ties keep reading order from the sort above.
    seen: set[str] = set()
    bullets: list[str] = []
    for _, rank, _, sentence, _ in chosen:
        key = _strip_diacritics(sentence.lower())[:80]
        if key in seen:
            continue
        seen.add(key)
        text = sentence.rstrip(",;: ")
        closing = "" if text.endswith((".", "!", "?", "…")) else "."
        bullets.append(f"- {text}{closing} [S{rank}]")
    if not bullets:
        return None
    # Follow the quoted text, not the question: the corpus is mostly Vietnamese,
    # so an English question answered from Vietnamese sources keeps a Vietnamese
    # lead-in instead of mixing languages.
    quote_text = " ".join(bullets)
    lead_vi = bool(_VI_CHARS.search(quote_text))
    header = ("Theo tài liệu nội bộ của DUSN-X:" if lead_vi
              else "From the DUSN-X internal documentation:")
    return header + "\n" + "\n".join(bullets)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build or inspect the local DUSN-X RAG index")
    parser.add_argument("--rebuild", action="store_true", help="reindex every document")
    parser.add_argument("--status", action="store_true", help="print index status and exit")
    parser.add_argument("--query", help="run a retrieval query")
    args = parser.parse_args()
    if args.status:
        print(index_status())
        sys.exit(0)
    if args.query:
        hits = retrieve(args.query)
        for hit in hits:
            print(f"{hit.score:7.2f} {hit.path}:{hit.start_line} {hit.heading}")
            print(hit.text[:300].replace("\n", " "))
            print()
        sys.exit(0)
    print(build_index(force=args.rebuild, verbose=True))
