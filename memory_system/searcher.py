from __future__ import annotations

import json
import math
import re
import sqlite3
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .config import DEFAULT_SOURCE_DIRS, WORKSPACE_ROOT
from .embeddings import EmbeddingClient
from .indexer import DEFAULT_DB_NAME, SCHEMA_VERSION


@dataclass
class SearchResult:
    chunk_id: int
    path: str
    title: str
    content: str
    snippet: str
    score: float
    source: str
    indexed_at: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)


class MemorySearcher:
    def __init__(self, root: Optional[str | Path] = None, db_path: Optional[str | Path] = None, **_: object) -> None:
        # 数据库路径保持在技能目录下，和索引器一致
        if root:
            self.source_dirs = [Path(root)]
        else:
            self.source_dirs = DEFAULT_SOURCE_DIRS
        self.db_path = Path(db_path) if db_path else (WORKSPACE_ROOT / "memory_system" / DEFAULT_DB_NAME)
        # [FIX] 挂载新的向量客户端
        self.embedding_client = EmbeddingClient()

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def search(
        self,
        query: str,
        limit: int = 10,
        use_semantic: bool = True,
        **_: object,
    ) -> list[SearchResult]:
        with self.connect() as conn:
            self._assert_schema_compatible(conn)
            keyword_results = self._keyword_search(conn, query, limit=limit * 3)
            # 从数据库获取 indexed_at 时间
            keyword_results = self._populate_indexed_at(conn, keyword_results)
            
            semantic_results = []
            if use_semantic:
                semantic_results = self._semantic_search(conn, query, limit=limit * 3)
                semantic_results = self._populate_indexed_at(conn, semantic_results)
        
        # 使用 RRF (Reciprocal Rank Fusion) 融合排名
        combined = self._rrf_combine_results(keyword_results, semantic_results)
        # 应用时间衰减 boost
        combined = self._apply_time_decay_boost(combined)
        combined.sort(key=lambda item: item.score, reverse=True)
        return combined[:limit]

    def search_json(self, query: str, limit: int = 10, use_semantic: bool = True, **kwargs: object) -> list[dict]:
        return [result.to_dict() for result in self.search(query=query, limit=limit, use_semantic=use_semantic, **kwargs)]

    def _assert_schema_compatible(self, conn: sqlite3.Connection) -> None:
        fts_row = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'chunks_fts'"
        ).fetchone()
        if not fts_row:
            raise RuntimeError("Index not found. Run build first.")
        fts_sql = fts_row[0] or ""
        columns = {
            row[1]: {"pk": row[5]}
            for row in conn.execute("PRAGMA table_info(chunks)").fetchall()
        }
        user_version = int(conn.execute("PRAGMA user_version").fetchone()[0] or 0)
        if (
            "id" not in columns
            or columns["id"]["pk"] != 1
            or "content='chunks'" not in fts_sql
            or "content_rowid='id'" not in fts_sql
            or user_version < SCHEMA_VERSION
        ):
            raise RuntimeError(
                "Detected an old/incompatible memory index schema. Re-run build to rebuild the index with the explicit chunks.id ↔ FTS mapping."
            )

    def _keyword_search(self, conn: sqlite3.Connection, query: str, limit: int) -> list[SearchResult]:
        stripped = query.strip()
        if not stripped:
            return []

        fts_results: list[SearchResult] = []
        try:
            fts_query = self._to_fts_query(stripped)
            if fts_query:
                rows = conn.execute(
                    """
                    SELECT
                        c.id AS chunk_id,
                        c.path,
                        COALESCE(c.title, '') AS title,
                        c.content,
                        snippet(chunks_fts, 1, '[', ']', ' … ', 18) AS snippet_text,
                        bm25(chunks_fts) AS raw_score
                    FROM chunks_fts
                    JOIN chunks c ON c.id = chunks_fts.rowid
                    WHERE chunks_fts MATCH ?
                    ORDER BY bm25(chunks_fts)
                    LIMIT ?
                    """,
                    (fts_query, limit),
                ).fetchall()
                fts_results = [
                    SearchResult(
                        chunk_id=int(row["chunk_id"]),
                        path=row["path"],
                        title=row["title"],
                        content=row["content"],
                        snippet=row["snippet_text"] or self._make_snippet(row["content"], stripped),
                        score=1.0 / (1.0 + max(0.0, float(row["raw_score"] or 0.0))),
                        source="keyword",
                    )
                    for row in rows
                ]
        except sqlite3.Error:
            fts_results = []

        if fts_results:
            return fts_results
        return self._fallback_keyword_search(conn, stripped, limit)

    def _fallback_keyword_search(self, conn: sqlite3.Connection, query: str, limit: int) -> list[SearchResult]:
        normalized_query = self._normalize_text(query)
        tokens = self._tokenize_query(normalized_query)
        if not tokens:
            tokens = [normalized_query]

        conditions = []
        params: list[object] = []
        score_terms = []
        for token in tokens:
            conditions.append("normalized_content LIKE ?")
            params.append(f"%{token}%")
            score_terms.append("CASE WHEN normalized_content LIKE ? THEN 1 ELSE 0 END")
            params.append(f"%{token}%")

        sql = f"""
            SELECT
                id AS chunk_id,
                path,
                COALESCE(title, '') AS title,
                content,
                ({' + '.join(score_terms) if score_terms else '0'}) AS matched_terms
            FROM chunks
            WHERE {' OR '.join(conditions) if conditions else '1=0'}
            ORDER BY matched_terms DESC, id DESC
            LIMIT ?
        """
        params.append(limit)
        rows = conn.execute(sql, params).fetchall()
        results: list[SearchResult] = []
        token_count = max(1, len(tokens))
        for row in rows:
            results.append(
                SearchResult(
                    chunk_id=int(row["chunk_id"]),
                    path=row["path"],
                    title=row["title"],
                    content=row["content"],
                    snippet=self._make_snippet(row["content"], query),
                    score=float(row["matched_terms"] or 0) / token_count,
                    source="keyword-fallback",
                )
            )
        return results

    def _semantic_search(self, conn: sqlite3.Connection, query: str, limit: int) -> list[SearchResult]:
        # 调用新客户端的方法获取查询向量，增加容错处理
        try:
            vectors = self.embedding_client.embed_texts([query])
            query_vec = vectors[0] if vectors else None
        except Exception as e:
            print(f"向量获取失败: {e}")
            return []

        if not query_vec or len(query_vec) < 2:
            return []

        # 查询时增加长度和非空检查
        rows = conn.execute(
            """
            SELECT id AS chunk_id, path, COALESCE(title, '') AS title,
                   content, length(embedding_json) as vec_len, embedding_json
            FROM chunks
            WHERE embedding_json IS NOT NULL
                  AND embedding_json != ''
                  AND length(embedding_json) > 2  -- 确保不是空数组
            """
        ).fetchall()

        scored: list[SearchResult] = []
        for row in rows:
            try:
                # 增加更严格的向量解析
                chunk_vec = json.loads(row["embedding_json"])

                # 检查向量类型和长度
                if not isinstance(chunk_vec, list) or len(chunk_vec) < 2:
                    continue
            except Exception:
                continue

            # 改进相似度计算，增加阈值过滤
            score = self._cosine_similarity(query_vec, chunk_vec)

            # 设置语义相似度阈值，过滤低相关性结果
            if score < 0.3:  # 可调整的阈值
                continue

            scored.append(
                SearchResult(
                    chunk_id=int(row["chunk_id"]),
                    path=row["path"],
                    title=row["title"],
                    content=row["content"],
                    snippet=self._make_snippet(row["content"], query),
                    score=score,
                    source="semantic",
                )
            )

        # 按语义相似度降序排序，并限制结果数量
        scored.sort(key=lambda item: item.score, reverse=True)
        return scored[:limit]

    def _populate_indexed_at(self, conn: sqlite3.Connection, results: list[SearchResult]) -> list[SearchResult]:
        """从数据库获取每个chunk所属文件的indexed_at时间"""
        path_to_time = {}
        for result in results:
            if result.path not in path_to_time:
                row = conn.execute(
                    "SELECT indexed_at FROM files WHERE path = ?", (result.path,)
                ).fetchone()
                path_to_time[result.path] = row["indexed_at"] if row else None
            result.indexed_at = path_to_time[result.path]
        return results

    def _rrf_combine_results(self, keyword_results: list[SearchResult], semantic_results: list[SearchResult], k: int = 60) -> list[SearchResult]:
        """
        Reciprocal Rank Fusion 融合多个排名结果，并去除重复的低分结果
        k = 60 是原论文推荐的参数，对大多数场景效果很好
        """
        # 构建 chunk_id -> result 的映射
        merged_map: dict[int, SearchResult] = {}

        # 收集所有唯一结果
        for result in keyword_results:
            merged_map[result.chunk_id] = result
        for result in semantic_results:
            if result.chunk_id not in merged_map:
                merged_map[result.chunk_id] = result

        # 获取各自的排名位置 (1-based)
        keyword_ranks = {result.chunk_id: rank + 1 for rank, result in enumerate(keyword_results)}
        semantic_ranks = {result.chunk_id: rank + 1 for rank, result in enumerate(semantic_results)}

        # 计算 RRF 得分
        for chunk_id, result in merged_map.items():
            rrf_score = 0.0
            source_parts = []
            if chunk_id in keyword_ranks:
                rrf_score += 1.0 / (k + keyword_ranks[chunk_id])
                source_parts.append("keyword")
            if chunk_id in semantic_ranks:
                rrf_score += 1.0 / (k + semantic_ranks[chunk_id])
                source_parts.append("semantic")
            result.score = rrf_score
            result.source = "+".join(source_parts) if len(source_parts) > 1 else source_parts[0] if source_parts else "unknown"

        # 去重策略：去除重复且低分的结果
        unique_results = {}
        for result in sorted(merged_map.values(), key=lambda x: x.score, reverse=True):
            # 使用路径和摘要作为唯一性判据
            key = (result.path, result.snippet)
            if key not in unique_results:
                unique_results[key] = result
            else:
                # 如果已存在结果，只保留分数更高的
                if result.score > unique_results[key].score:
                    unique_results[key] = result

        return list(unique_results.values())

    def _apply_time_decay_boost(self, results: list[SearchResult], half_life_days: float = 180.0) -> list[SearchResult]:
        """
        时间衰减boost：越新的记忆得分越高
        使用指数衰减: boost = exp(-lambda * days_ago), 其中 lambda = ln(2) / half_life_days
        half_life_days = 180 表示半年后得分衰减一半
        """
        now = datetime.now(timezone.utc)
        lam = math.log(2) / half_life_days
        
        for result in results:
            if not result.indexed_at:
                continue  # 没有时间信息不调整
                
            try:
                # 解析 indexed_at (ISO 8601 format)
                if result.indexed_at.endswith("Z"):
                    dt_indexed = datetime.fromisoformat(result.indexed_at.replace("Z", "+00:00"))
                else:
                    dt_indexed = datetime.fromisoformat(result.indexed_at)
                
                # 确保是UTC时间
                if dt_indexed.tzinfo is None:
                    dt_indexed = dt_indexed.replace(tzinfo=timezone.utc)
                
                # 计算天数差
                days_ago = (now - dt_indexed).total_seconds() / (24 * 3600)
                if days_ago < 0:
                    days_ago = 0  # 未来的时间不惩罚
                
                # 指数衰减 boost
                boost = math.exp(-lam * days_ago)
                # 缩放范围到 [1.0 - 0.5, 1.0]，不要把老记忆压太低
                # 最新 = 1.0, 半衰 = 0.75, 两倍半衰 = 0.625
                scaled_boost = 0.5 + 0.5 * boost
                
                # 应用到得分
                result.score = result.score * scaled_boost
                
            except Exception:
                # 解析失败就跳过
                continue
        
        return results

    def _legacy_combine_results(self, keyword_results: list[SearchResult], semantic_results: list[SearchResult]) -> list[SearchResult]:
        """保留原硬编码加权作为备份"""
        merged: dict[int, SearchResult] = {}
        for result in keyword_results:
            merged[result.chunk_id] = result
        for result in semantic_results:
            existing = merged.get(result.chunk_id)
            if existing is None:
                merged[result.chunk_id] = result
                continue
            existing.score = max(existing.score, 0.0) + (result.score * 0.35)
            if existing.source != result.source:
                existing.source = "hybrid"
        return list(merged.values())

    @staticmethod
    def _normalize_text(text: str) -> str:
        return re.sub(r"\s+", " ", text).strip().lower()

    @classmethod
    def _tokenize_query(cls, query: str) -> list[str]:
        if re.search(r"[\u4e00-\u9fff]", query):
            compact = query.replace(" ", "")
            return [compact[i:j] for i in range(len(compact)) for j in range(i + 2, min(len(compact), i + 5) + 1)] or [compact]
        return [token for token in re.split(r"[^\w]+", query) if token]

    @classmethod
    def _to_fts_query(cls, query: str) -> str:
        if re.search(r"[\u4e00-\u9fff]", query):
            compact = query.replace(" ", "")
            if compact:
                return ' OR '.join(f'"{compact[i:j]}"' for i in range(len(compact)) for j in range(i + 2, min(len(compact), i + 5) + 1))
            return ""
        tokens = [token for token in re.split(r"[^\w]+", query) if token]
        return " AND ".join(f'"{token}"' for token in tokens)

    @staticmethod
    def _make_snippet(content: str, query: str, window: int = 160) -> str:
        text = re.sub(r"\s+", " ", content).strip()
        if not text:
            return ""
        lowered = text.lower()
        q = query.lower().strip()
        if not q:
            return text[:window]
        idx = lowered.find(q)
        if idx == -1 and re.search(r"[\u4e00-\u9fff]", q):
            for size in range(min(4, len(q)), 1, -1):
                for start in range(0, len(q) - size + 1):
                    idx = lowered.find(q[start : start + size])
                    if idx != -1:
                        break
                if idx != -1:
                    break
        if idx == -1:
            return text[:window]
        start = max(0, idx - window // 3)
        end = min(len(text), start + window)
        snippet = text[start:end]
        if start > 0:
            snippet = "… " + snippet
        if end < len(text):
            snippet += " …"
        return snippet

    @staticmethod
    def _cosine_similarity(a: list[float], b: list[float]) -> float:
        size = min(len(a), len(b))
        if size == 0:
            return 0.0
        dot = sum(float(a[i]) * float(b[i]) for i in range(size))
        norm_a = math.sqrt(sum(float(a[i]) * float(a[i]) for i in range(size)))
        norm_b = math.sqrt(sum(float(b[i]) * float(b[i]) for i in range(size)))
        if norm_a == 0.0 or norm_b == 0.0:
            return 0.0
        return dot / (norm_a * norm_b)