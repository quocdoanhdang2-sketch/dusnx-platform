"""Deterministic answers for plain arithmetic.

Small local models state plainly wrong results (a 1.5B model answered 2+2=5),
so simple expressions are evaluated here instead of being generated.
"""
from __future__ import annotations

import ast
import re

_CUE = re.compile(
    r"(?i)(?:\?|bằng\s+(?:mấy|bao\s+nhiêu)|là\s+(?:mấy|bao\s+nhiêu)|"
    r"equals?|equal\s+to|how\s+much\s+is|calculate|compute|tính\s+)"
)
_LEAD = re.compile(
    r"(?i)^\s*(?:hãy\s+|giúp\s+(?:tôi|mình)\s+|please\s+|can\s+you\s+)?"
    r"(?:tính(?:\s+giúp(?:\s+tôi)?)?|toán|calculate|compute|how\s+much\s+is|"
    r"what\s+is|what's|whats)?\s*"
)
_TAIL = re.compile(
    r"(?i)\s*(?:bằng\s+(?:mấy|bao\s+nhiêu)|là\s+(?:mấy|bao\s+nhiêu)|"
    r"equals?|equal\s+to)\s*\??\s*$"
)
_ONLY_EXPRESSION = re.compile(r"^[0-9+\-*/(). ]+$")
_MULTIPLY_X = re.compile(r"(?<=\d)\s*[xX]\s*(?=\d)")


class _UnsafeExpression(ValueError):
    pass


def _evaluate(node: ast.AST) -> float:
    if isinstance(node, ast.Expression):
        return _evaluate(node.body)
    if isinstance(node, ast.Constant):
        if type(node.value) not in (int, float):
            raise _UnsafeExpression("non-numeric")
        return float(node.value)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        value = _evaluate(node.operand)
        return -value if isinstance(node.op, ast.USub) else value
    if isinstance(node, ast.BinOp):
        left, right = _evaluate(node.left), _evaluate(node.right)
        if isinstance(node.op, ast.Add):
            return left + right
        if isinstance(node.op, ast.Sub):
            return left - right
        if isinstance(node.op, ast.Mult):
            return left * right
        if isinstance(node.op, ast.Div):
            if right == 0:
                raise ZeroDivisionError
            return left / right
        if isinstance(node.op, ast.Mod):
            if right == 0:
                raise ZeroDivisionError
            return left % right
    raise _UnsafeExpression("unsupported_operator")


def _format_number(value: float) -> str:
    if abs(value) < 1e15 and float(value).is_integer():
        return str(int(value))
    rounded = round(value, 10)
    text = f"{rounded:.10f}".rstrip("0").rstrip(".")
    return text or "0"


def answer_arithmetic_question(message: str, language: str = "vi") -> str | None:
    text = (message or "").strip()
    if not text or len(text) > 80 or not re.search(r"\d", text):
        return None
    if not _CUE.search(text):
        return None
    candidate = _MULTIPLY_X.sub("*", text)
    candidate = _LEAD.sub("", candidate)
    candidate = _TAIL.sub("", candidate).strip()
    candidate = candidate.rstrip("?").strip()
    if candidate.endswith("="):
        candidate = candidate[:-1].strip()
    if not candidate or not _ONLY_EXPRESSION.match(candidate):
        return None
    if not re.search(r"[+\-*/%]", candidate):
        return None
    digits = re.findall(r"\d+(?:\.\d+)?", candidate)
    if len(digits) < 2:
        return None
    if any(float(value) > 1e12 for value in digits):
        return None
    try:
        tree = ast.parse(candidate, mode="eval")
        result = _evaluate(tree)
    except ZeroDivisionError:
        return ("Không thể chia cho 0." if language != "en"
                else "Division by zero is undefined.")
    except (SyntaxError, ValueError, _UnsafeExpression):
        return None
    if result != result or result in (float("inf"), float("-inf")) or abs(result) > 1e15:
        return None
    display = re.sub(r"\s+", " ", candidate)
    return f"{display} = {_format_number(result)}"
