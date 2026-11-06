"""Deterministic Vietnamese/English policy used before any LLM call."""
from __future__ import annotations

import re
import unicodedata

SUPPORTED = {"auto", "vi", "en"}
VI_WORDS = {
    "bạn", "tôi", "mình", "là", "và", "không", "có", "hãy", "đang", "đã", "muốn",
    "trả", "lời", "bằng", "tiếng", "của", "trong", "với", "này", "các", "những",
    "được", "cho", "về", "nó", "một", "những", "để", "từ", "khi", "thì",
}
EN_WORDS = {
    "the", "is", "are", "you", "please", "what", "which", "how", "why", "where", "when",
    "answer", "english", "vietnamese", "from", "now", "briefly", "explain", "database",
    "indexing", "improves", "query", "performance", "system", "features", "core", "benefits",
    "with", "this", "that", "about", "can", "could", "should", "would", "will", "have", "has",
    "for", "and", "or", "in", "on", "at", "to", "by", "of", "it", "its", "software", "data",
}
VI_DIACRITICS = re.compile(r"[ăâđêôơưáàảãạấầẩẫậắằẳẵặéèẻẽẹếềểễệíìỉĩịóòỏõọốồổỗộớờởỡợúùủũụứừửữựýỳỷỹỵ]", re.I)


def detect_language(text: str, previous: str | None = None) -> str:
    normalized = unicodedata.normalize("NFC", text).casefold()
    words = set(re.findall(r"[\w]+", normalized, flags=re.UNICODE))
    if len(normalized.strip()) <= 5 and previous in {"vi", "en"}:
        return previous
    vi = len(VI_DIACRITICS.findall(normalized)) * 2 + len(words & VI_WORDS)
    en = len(words & EN_WORDS)
    if vi > en and vi:
        return "vi"
    if en > vi and en:
        return "en"
    return "unknown"


def response_language(preference: str, detected: str, previous: str | None = None) -> str:
    preference = preference if preference in SUPPORTED else "auto"
    if preference in {"vi", "en"}:
        return preference
    if detected in {"vi", "en"}:
        return detected
    return previous if previous in {"vi", "en"} else "vi"


def preference_instruction(text: str) -> str | None:
    value = unicodedata.normalize("NFC", text).casefold().strip()
    if re.search(r"(?:từ giờ|kể từ giờ).*(?:tiếng anh|english)|answer in english from now on", value):
        return "en"
    if re.search(r"(?:từ giờ|kể từ giờ).*(?:tiếng việt|vietnamese)|answer in vietnamese from now on", value):
        return "vi"
    return None


_NON_LATIN_SCRIPTS = {
    "arabic": re.compile(r"[\u0600-\u06ff]"),
    "cyrillic": re.compile(r"[\u0400-\u052f]"),
    "devanagari": re.compile(r"[\u0900-\u097f]"),
    "greek": re.compile(r"[\u0370-\u03ff]"),
    "han": re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]"),
    "hangul": re.compile(r"[\uac00-\ud7af\u1100-\u11ff]"),
    "hebrew": re.compile(r"[\u0590-\u05ff]"),
    "hiragana_katakana": re.compile(r"[\u3040-\u30ff]"),
    "thai": re.compile(r"[\u0e00-\u0e7f]"),
}


def _natural_language_text(text: str) -> str:
    """Ignore markup and clearly delimited literal material during script checks."""
    text = re.sub(r"```.*?```", " ", text, flags=re.DOTALL)
    text = re.sub(r"`[^`]*`", " ", text)
    text = re.sub(r"https?://\S+|\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b", " ", text)
    # Quoted source text, labels, and proper names are not evidence of the prose language.
    text = re.sub(r"“[^”]*”|‘[^’]*’|\"[^\"]*\"|(?<!\w)'[^'\n]{2,}'(?!\w)", " ", text)
    # Names following common attribution phrases are not prose-language samples.
    text = re.sub(
        r"(?i)(?:(?<=\bby )(?:[A-ZÀ-Ỵ][\w'’-]*\s+){1,}[A-ZÀ-Ỵ][\w'’-]*|"
        r"(?<=\bbởi )(?:[A-ZÀ-Ỵ][\w'’-]*\s+){1,}[A-ZÀ-Ỵ][\w'’-]*)",
        " ", text,
    )
    return text


def _confident_segment_language(segment: str) -> str | None:
    """Return a prose language only when one language has several independent signals."""
    normalized = unicodedata.normalize("NFC", segment).casefold()
    words = set(re.findall(r"[\w]+", normalized, flags=re.UNICODE))
    vi_marks = len(VI_DIACRITICS.findall(normalized))
    vi_words = len(words & VI_WORDS)
    en_words = len(words & EN_WORDS)
    vi_score = vi_marks * 2 + vi_words
    en_score = en_words
    # Requiring multiple signals reduces false positives from product names,
    # short headings, and isolated technical terms.
    if vi_score >= 5 and vi_score > en_score and (vi_words >= 1 or vi_marks >= 6):
        return "vi"
    if en_words >= 3 and en_score >= vi_score + 3:
        return "en"
    return None


def assess_response_language(text: str, expected: str) -> dict:
    """Assess prose language independently of response-language metadata.

    Script anomalies are only counted outside code, URLs, and quoted literals so
    identifiers, examples, and explicitly quoted source text do not fail a turn.
    The result is a conservative heuristic; it does not claim semantic review.
    """
    prose = _natural_language_text(text or "")
    actual = detect_language(prose)
    scripts = {name: len(pattern.findall(prose)) for name, pattern in _NON_LATIN_SCRIPTS.items()}
    # A lone Greek/math symbol or a single non-Latin proper-name character is
    # not strong evidence that the prose switched languages.
    scripts = {name: count for name, count in scripts.items() if count >= 2}
    scripts = {name: count for name, count in scripts.items() if count}
    latin_letters = len(re.findall(r"[A-Za-zÀ-ɏ]", prose))
    segments = [part.strip() for part in re.split(r"(?:\r?\n|(?<=[.!?])\s+)", prose) if part.strip()]
    segment_languages = [language for part in segments
                         if (language := _confident_segment_language(part)) is not None]
    has_expected_segment = expected in segment_languages
    has_other_segment = any(language in {"vi", "en"} and language != expected
                            for language in segment_languages)
    mixed_segments = bool(has_expected_segment and has_other_segment)

    if scripts and latin_letters:
        status = "mixed"
    elif scripts:
        status = "divergent"
        actual = "other_script"
    elif mixed_segments:
        status = "mixed"
    elif actual == expected:
        status = "matched"
    elif actual in {"vi", "en"}:
        status = "divergent"
    else:
        status = "uncertain"
    return {
        "status": status,
        "actual_language": actual,
        "expected_language": expected,
        "unsupported_script_counts": scripts,
        "mixed_language_segments": sum(1 for language in segment_languages if language != expected),
        "method": "lexical_and_unicode_script_heuristic",
        "limitation": "Segment-level lexical signals are heuristic; proper names and short technical phrases are intentionally insufficient on their own. Does not judge task correctness or factuality.",
    }
