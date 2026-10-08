from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List

EXCLUDED_KINDS = {"parameter", "keyword", "string", "number", "comment", "operator", "regexp",
                  "modifier", "label", "typeParameter"}


@dataclass(frozen=True)
class Token:
    line: int
    col: int
    length: int
    kind: str


def utf16_len(text: str) -> int:
    return len(text.encode("utf-16-le")) // 2


def token_text(line_text: str, col: int, length: int) -> str:
    encoded = line_text.encode("utf-16-le")
    return encoded[col * 2:(col + length) * 2].decode("utf-16-le", errors="replace")


def decode_semantic_tokens(data: List[int], token_types: List[str]) -> List[Token]:
    tokens: List[Token] = []
    line = col = 0
    for index in range(0, len(data) - 4, 5):
        delta_line, delta_col, length, kind_index, _ = data[index:index + 5]
        line += delta_line
        col = col + delta_col if delta_line == 0 else delta_col
        kind = token_types[kind_index] if kind_index < len(token_types) else "unknown"
        tokens.append(Token(line=line, col=col, length=length, kind=kind))
    return tokens


def regex_tokens(lines: List[str], pattern: str, start0: int, end0: int) -> List[Token]:
    compiled = re.compile(pattern)
    tokens: List[Token] = []
    for line0 in range(start0, min(end0, len(lines) - 1) + 1):
        text = lines[line0]
        for match in compiled.finditer(text):
            tokens.append(Token(line=line0, col=utf16_len(text[:match.start()]),
                                length=utf16_len(match.group(0)), kind="unknown"))
    return tokens


def linkable(tokens: List[Token]) -> List[Token]:
    return [token for token in tokens if token.kind not in EXCLUDED_KINDS]
