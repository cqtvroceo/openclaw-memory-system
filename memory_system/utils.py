from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Iterable, List

CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]+")
WORD_RE = re.compile(r"[A-Za-z0-9_]+")
WHITESPACE_RE = re.compile(r"\s+")


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()


def expand_targets(root: Path, patterns: Iterable[str]) -> List[Path]:
    files = []
    seen = set()
    for pattern in patterns:
        matches = root.glob(pattern)
        for path in matches:
            if path.is_file():
                resolved = path.resolve()
                if resolved not in seen:
                    seen.add(resolved)
                    files.append(resolved)
    files.sort()
    return files


def chunk_text(text: str, chunk_size: int = 1200, overlap: int = 150) -> list[tuple[int, str]]:
    text = text.strip()
    if not text:
        return []
    if len(text) <= chunk_size:
        return [(0, text)]

    chunks = []
    start = 0
    idx = 0
    step = max(1, chunk_size - overlap)
    while start < len(text):
        end = min(len(text), start + chunk_size)
        chunk = text[start:end].strip()
        if chunk:
            chunks.append((idx, chunk))
            idx += 1
        if end >= len(text):
            break
        start += step
    return chunks


def cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(y * y for y in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def normalize_text(text: str) -> str:
    return WHITESPACE_RE.sub(" ", text.strip().lower())


def extract_title(text: str, fallback: str) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            title = stripped.lstrip("#").strip()
            return title[:120] if title else fallback
        return stripped[:120]
    return fallback


def build_query_terms(query: str) -> list[tuple[str, float]]:
    seen: set[str] = set()
    weighted_terms: list[tuple[str, float]] = []

    def push(term: str, weight: float) -> None:
        term = term.strip().lower()
        if len(term) < 1 or term in seen:
            return
        seen.add(term)
        weighted_terms.append((term, weight))

    normalized_query = normalize_text(query)
    if normalized_query:
        push(normalized_query, 8.0)

    for word in WORD_RE.findall(query):
        push(word, 4.0)

    for phrase in CJK_RE.findall(query):
        push(phrase, 6.0)
        if len(phrase) >= 2:
            for i in range(len(phrase) - 1):
                push(phrase[i : i + 2], 3.0)
        for char in phrase:
            push(char, 1.0)

    return weighted_terms


def make_snippet(content: str, query: str, max_chars: int = 160) -> str:
    text = WHITESPACE_RE.sub(" ", content.strip())
    if len(text) <= max_chars:
        return text

    candidates = [query.strip()]
    candidates.extend(term for term, _ in build_query_terms(query))

    lower_text = text.lower()
    hit_pos = -1
    hit_term = ""
    for candidate in candidates:
        candidate = candidate.strip().lower()
        if not candidate:
            continue
        pos = lower_text.find(candidate)
        if pos != -1:
            hit_pos = pos
            hit_term = candidate
            break

    if hit_pos == -1:
        return text[: max_chars - 1] + "…"

    focus = hit_pos + max(1, len(hit_term)) // 2
    start = max(0, focus - max_chars // 2)
    end = min(len(text), start + max_chars)
    snippet = text[start:end]
    if start > 0:
        snippet = "…" + snippet
    if end < len(text):
        snippet = snippet + "…"
    return snippet
