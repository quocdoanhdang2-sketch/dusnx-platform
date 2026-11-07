"""Tests for the grounded retrieval module (no network, no live index needed).

These pin the behaviours that keep extractive answers faithful to the
repository: the retrieval gate stays on-domain, quoted passages carry their
citation, and code questions quote a declaration and docstring rather than
arbitrary statements.
"""
from apps.ai_api import rag


def hit(text: str, *, path: str = "docs/ARCHITECTURE.md",
        title: str = "DUSN-X Architecture", heading: str = "DUSN-X > 2 Kiến trúc",
        start_line: int = 10) -> rag.Hit:
    return rag.Hit(path, title, heading, start_line, start_line + 5, text,
                   120.0, 0.0, coverage=1.0)


# ── Retrieval gate ───────────────────────────────────────────────────────────

def test_gate_accepts_vietnamese_english_and_accentless_domain_questions():
    for query in (
        "DUSN-X là gì?",
        "kiến trúc DUSN-X gồm những tầng nào?",
        "kien truc he thong gom nhung tang nao?",
        "mật khẩu được hash bằng gì?",
        "mat khau duoc hash bang gi?",
        "What does the DUSN-X gateway do?",
        "answer_from_hits trả về gì?",
    ):
        assert rag.should_retrieve(query), query


def test_gate_rejects_general_knowledge_and_small_talk():
    for query in (
        "thời tiết Hà Nội hôm nay thế nào?",
        "python là gì?",
        "cảm ơn nhé",
        "cho tôi một bài thơ",
        "",
    ):
        assert not rag.should_retrieve(query), query


# ── Extractive answers ───────────────────────────────────────────────────────

def test_answer_quotes_passage_with_citation():
    answer = rag.answer_from_hits(
        "kiến trúc DUSN-X gồm những tầng nào?",
        [hit("Kiến trúc hệ thống DUSN-X hiện hành gồm bốn tầng: Client, Gateway, AI API và dữ liệu.")])
    assert answer is not None
    assert answer.startswith("Theo tài liệu nội bộ của DUSN-X:")
    assert "bốn tầng" in answer
    assert "[S1]" in answer


def test_answer_header_follows_quoted_language():
    english = rag.answer_from_hits(
        "What does the gateway do?",
        [hit("The gateway is the only boundary and proxies allowlisted /v1 routes.")])
    assert english is not None and english.startswith("From the DUSN-X internal documentation:")


def test_answer_returns_none_without_matching_passage():
    assert rag.answer_from_hits("cấu hình Ollama provider", [
        hit("Một câu hoàn toàn không liên quan về nấu ăn và thời tiết.")]) is None


def test_definition_query_quotes_signature_and_docstring():
    source = (
        "def answer_from_hits(query: str, hits: list[Hit], language: str = \"vi\",\n"
        "                     max_sentences: int = 3) -> Optional[str]:\n"
        "    \"\"\"Return a cited answer.\n\n"
        "    Returns None when no passage is relevant enough.\n"
        "    \"\"\"\n"
        "    if not hits:\n"
        "        return None\n"
    )
    answer = rag.answer_from_hits(
        "answer_from_hits trả về gì?",
        [hit(source, path="python/apps/ai_api/rag.py", heading="rag.py")])
    assert answer is not None
    assert "def answer_from_hits" in answer
    assert "Returns None when no passage is relevant enough." in answer
    assert "if not hits" not in answer


def test_code_statements_are_not_quoted_as_answers():
    source = (
        "extractive = (rag.answer_from_hits(req.message, rag_hits) if rag_hits else None)\n"
        "if extractive: reply_text, provider_ok = extractive, True\n"
    )
    assert rag.answer_from_hits(
        "cấu hình Ollama provider",
        [hit(source, path="python/apps/ai_api/main.py", heading="main.py")]) is None


def test_table_header_fragment_is_skipped():
    header = "Auth — Memory — Gateway — Provider — Add-in — Router"
    body = "Gateway là biên giới duy nhất, proxy allowlist /api/v1/* và giữ nguyên Authorization."
    answer = rag.answer_from_hits(
        "gateway làm gì?",
        [hit(f"{header}\n\n{body}")])
    assert answer is not None
    assert "Auth — Memory" not in answer
    assert "biên giới duy nhất" in answer
