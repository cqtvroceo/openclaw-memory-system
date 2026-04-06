from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent


def run_cli_search(query: str) -> list[dict[str, Any]]:
    cmd = [sys.executable, "-m", "memory_system.cli", "search", query, "--json"]
    proc = subprocess.run(
        cmd,
        cwd=str(WORKSPACE_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if proc.returncode != 0:
        raise RuntimeError(f"search failed: {proc.stderr.strip() or proc.stdout.strip()}")

    payload = json.loads(proc.stdout)
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in ("results", "hits", "items", "data"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
    raise RuntimeError("unexpected search JSON shape")


def ensure_index() -> None:
    marker_candidates = [
        WORKSPACE_ROOT / ".memory_system",
        WORKSPACE_ROOT / "memory_system" / ".index",
        WORKSPACE_ROOT / "memory_system" / "index.sqlite",
        WORKSPACE_ROOT / ".memory_index.sqlite",
        WORKSPACE_ROOT / "memory_system" / "memory_index.sqlite",
        WORKSPACE_ROOT / "memory_system" / "memory_index.sqlite3",
        WORKSPACE_ROOT / "memory_index.sqlite",
        WORKSPACE_ROOT / "memory_index.sqlite3",
    ]
    if any(path.exists() for path in marker_candidates):
        return

    cmd = [sys.executable, "-m", "memory_system.cli", "build", "--json"]
    proc = subprocess.run(
        cmd,
        cwd=str(WORKSPACE_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if proc.returncode != 0:
        raise RuntimeError(f"build failed: {proc.stderr.strip() or proc.stdout.strip()}")


def normalize_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


def extract_path(item: dict[str, Any]) -> str:
    for key in ("path", "source", "file", "filepath", "relative_path"):
        value = normalize_text(item.get(key))
        if value:
            return value.replace("\\", "/")
    return "(unknown source)"


def extract_snippet(item: dict[str, Any]) -> str:
    for key in ("snippet", "summary", "text", "content", "excerpt", "chunk_text"):
        value = normalize_text(item.get(key))
        if value:
            return re.sub(r"\s+", " ", value)
    return ""


def extract_title(item: dict[str, Any], path: str) -> str:
    for key in ("title", "heading", "name"):
        value = normalize_text(item.get(key))
        if value:
            return value
    return Path(path).name


def extract_score(item: dict[str, Any]) -> float | None:
    for key in ("score", "final_score", "similarity", "hybrid_score"):
        value = item.get(key)
        if isinstance(value, (int, float)):
            return float(value)
        try:
            if value is not None:
                return float(value)
        except Exception:
            pass
    return None


def tokenize_query(query: str, min_token_length: int = 2) -> list[str]:
    import re
    import unicodedata

    # 更全面的领域词库和语义映射
    TECH_KEYWORDS = {
        # 技术领域分类
        '编程语言': ['python', 'java', 'javascript', 'c++', 'ruby', 'rust', 'go', 'typescript'],
        '开发技术': ['全栈', '前端', '后端', '微服务', '分布式', '云原生', 'serverless'],
        '数据处理': ['数据库', '存储', '缓存', '数据分析', '数据挖掘', '大数据'],
        '人工智能': ['机器学习', '深度学习', '神经网络', '自然语言处理', '计算机视觉', 'ai'],
        '系统架构': ['微服务', '分布式系统', '高并发', '性能优化', '负载均衡', '架构设计'],
        '软件工程': ['敏捷开发', '测试', '持续集成', 'devops', '代码质量', '重构']
    }

    # 规范化处理
    def normalize_token(token):
        # 处理全角转半角
        token = unicodedata.normalize('NFKC', token)
        # 统一转换为小写
        return token.lower().strip()

    # 智能分词函数
    def advanced_tokenize(text):
        tokens = []

        # 正则模式
        patterns = [
            r"[\u4e00-\u9fff]+",  # 中文词
            r"[A-Za-z0-9_]+",     # 英文和数字
            r"\w+",               # 驼峰和下划线命名
        ]

        for pattern in patterns:
            matches = re.findall(pattern, text)
            for match in matches:
                # 处理驼峰命名
                if any(c.isupper() for c in match[1:]):
                    # 拆分驼峰命名
                    camel_tokens = re.findall(r'[A-Z]?[a-z]+|[A-Z]+(?=[A-Z][a-z]|\d|\W|$)|\d+', match)
                    tokens.extend(camel_tokens)

                # 下划线命名
                if '_' in match:
                    tokens.extend(match.split('_'))

                tokens.append(match)

        return tokens

    # 领域关联分词
    def domain_extend(tokens):
        extended_tokens = set()
        for token in tokens:
            # 精确匹配领域关键词
            for category, keywords in TECH_KEYWORDS.items():
                if token in keywords:
                    extended_tokens.add(category)
                    extended_tokens.update(keywords)
        return list(extended_tokens)

    # 核心分词逻辑
    base_tokens = advanced_tokenize(query)

    # 规范化处理
    processed_tokens = [
        normalize_token(token)
        for token in base_tokens
        if len(normalize_token(token)) >= min_token_length
    ]

    # 去重
    processed_tokens = list(dict.fromkeys(processed_tokens))

    # 领域扩展
    domain_tokens = domain_extend(processed_tokens)

    # 合并去重
    all_tokens = list(dict.fromkeys(processed_tokens + domain_tokens))

    return all_tokens


def choose_focus_lines(snippet: str, query: str, max_lines: int = 2) -> list[str]:
    if not snippet:
        return []

    query_terms = tokenize_query(query)
    parts = re.split(r"[\r\n]+|(?<=[。！？.!?])\s+|\s*[-*]\s+", snippet)
    lines = [re.sub(r"\s+", " ", part).strip(" -•\t") for part in parts if part.strip()]

    scored: list[tuple[int, str]] = []
    for line in lines:
        lowered = line.lower()
        score = sum(1 for term in query_terms if term in lowered)
        if score > 0:
            scored.append((score, line))

    if not scored:
        return lines[:max_lines]

    scored.sort(key=lambda x: (-x[0], len(x[1])))
    selected: list[str] = []
    for _, line in scored:
        if line not in selected:
            selected.append(line)
        if len(selected) >= max_lines:
            break
    return selected


def compress_text(text: str, limit: int = 140) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def calculate_jaccard_similarity(set1: list[str], set2: list[str]) -> float:
    """计算Jaccard相似度"""
    intersection = set(set1) & set(set2)
    union = set(set1) | set(set2)
    return len(intersection) / len(union) if union else 0

def infer_why(path: str, snippet: str, query: str) -> str:
    reasons: list[str] = []

    # 标准化处理
    lowered_path = path.lower()
    lowered_snippet = snippet.lower()
    lowered_query = query.lower()

    # 领域关键词映射
    domain_mapping = {
        '数据库': ['sqlite', 'database', 'connection', '存储', '查询'],
        '机器学习': ['模型', 'model', 'train', 'learning', '算法'],
        '系统开发': ['架构', 'system', '设计', 'framework', '开发'],
        '性能': ['优化', 'performance', 'speed', '加速', '效率']
    }

    # 1. 路径匹配
    path_match_hints = [
        (domain, keywords)
        for domain, keywords in domain_mapping.items()
        if any(keyword in lowered_path for keyword in keywords)
    ]
    if path_match_hints:
        domain_hints = [domain for domain, _ in path_match_hints]
        reasons.append(f"文件路径属于领域：{' | '.join(domain_hints)}")

    # 2. 分词与语义分析
    query_tokens = tokenize_query(query)
    snippet_tokens = tokenize_query(snippet)

    # 计算多维度相似度指标
    jaccard_similarity = calculate_jaccard_similarity(query_tokens, snippet_tokens)

    # Token重叠分析
    semantic_overlap = [token for token in query_tokens if token in snippet_tokens]

    # 专业术语权重
    professional_weight = {
        '数据库': 1.5,
        '连接': 1.3,
        '方法': 1.2,
        '系统': 1.1
    }

    # 根据专业术语调整相似度
    weighted_score = sum(
        professional_weight.get(token, 1.0) for token in semantic_overlap
    ) / len(semantic_overlap) if semantic_overlap else 0

    # 上下文语义线索
    context_clues = {
        "实现细节": ["如何", "步骤", "方法"],
        "使用场景": ["应用", "场景", "例子"],
        "限制条件": ["注意", "风险", "边界"]
    }

    for clue_type, clue_keywords in context_clues.items():
        if any(keyword in lowered_query and keyword in lowered_snippet for keyword in clue_keywords):
            reasons.append(f"检测到{clue_type}相关线索")

    # 最终语义强度评估
    if jaccard_similarity > 0.5:
        reasons.append(f"语义匹配强度：{jaccard_similarity:.0%}")
    elif jaccard_similarity > 0.3:
        reasons.append(f"语义匹配度：{jaccard_similarity:.0%}")

    # 专业术语重叠
    if semantic_overlap:
        reasons.append(f"关键词重叠：{' | '.join(semantic_overlap[:3])}")

    # 最终降级策略
    if not reasons:
        reasons.append("语义相似但未找到直接关联")

    return reasons[0] if reasons else "未找到直接关联"


def build_context_pack(query: str, results: list[dict[str, Any]], max_items: int = 3) -> dict[str, Any]:
    packaged_items: list[dict[str, Any]] = []
    for item in results[:max_items]:
        path = extract_path(item)
        snippet = extract_snippet(item)
        focus_lines = choose_focus_lines(snippet, query)
        summary = " / ".join(compress_text(line, 90) for line in focus_lines if line)
        if not summary:
            summary = compress_text(snippet or extract_title(item, path), 90)

        packaged_items.append(
            {
                "title": extract_title(item, path),
                "source": path,
                "score": extract_score(item),
                "summary": summary,
                "why": infer_why(path, snippet, query),
            }
        )

    injection_lines = [f"问题: {query}"]
    for idx, item in enumerate(packaged_items, start=1):
        line = f"{idx}. {item['summary']} (source: {item['source']}; why: {item['why']})"
        injection_lines.append(compress_text(line, 220))

    return {
        "query": query,
        "result_count": len(results),
        "selected_count": len(packaged_items),
        "pack_principle": "只注入命中摘要 + 来源 + why；不注入全文。",
        "context_items": packaged_items,
        "suggested_injection": "\n".join(injection_lines),
    }


def format_pack(pack: dict[str, Any]) -> str:
    lines = [
        "# Minimal Context Pack",
        "",
        f"- Query: {pack['query']}",
        f"- Search hits: {pack['result_count']}",
        f"- Selected: {pack['selected_count']}",
        f"- Principle: {pack['pack_principle']}",
        "",
        "## Suggested injection",
        "",
        pack["suggested_injection"],
        "",
        "## Selected memory items",
        "",
    ]
    for idx, item in enumerate(pack["context_items"], start=1):
        score = "" if item["score"] is None else f" | score={item['score']:.4f}"
        lines.extend(
            [
                f"### {idx}. {item['title']}",
                f"- source: {item['source']}{score}",
                f"- summary: {item['summary']}",
                f"- why: {item['why']}",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a minimal context pack from memory_system search results.")
    parser.add_argument("query", help="User query to retrieve memory for")
    parser.add_argument("--max-items", type=int, default=3, help="How many hits to keep in the final pack")
    parser.add_argument("--json", action="store_true", help="Print JSON instead of markdown")
    parser.add_argument("--skip-build", action="store_true", help="Do not auto-build index if missing")
    args = parser.parse_args(argv)

    if not args.skip_build:
        ensure_index()
    results = run_cli_search(args.query)
    pack = build_context_pack(args.query, results, max_items=max(1, args.max_items))
    if args.json:
        print(json.dumps(pack, ensure_ascii=False, indent=2))
    else:
        print(format_pack(pack))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
