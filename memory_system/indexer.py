from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from fnmatch import fnmatch
from pathlib import Path
from typing import Iterator, Optional
from .config import DEFAULT_IGNORE_GLOBS, DEFAULT_SOURCE_DIRS, DEFAULT_TARGETS, WORKSPACE_ROOT
from .embeddings import EmbeddingClient

# [UPDATE] 提升了 Schema 版本号，强制触发 SQLite 重建，避免旧的垃圾数据残留
SCHEMA_VERSION = 4
DEFAULT_DB_NAME = "memory_index.sqlite3"
TEXT_EXTENSIONS = {
    ".md", ".markdown", ".txt", ".rst",
    ".py", ".js", ".ts", ".tsx", ".jsx",
    ".json", ".jsonl", ".yaml", ".yml", ".toml", ".ini", ".cfg",
    ".sh", ".ps1", ".bat", ".cmd",
    ".html", ".htm", ".css", ".sql",
}
SKIP_DIRS = {
    ".git", ".hg", ".svn", "node_modules", "dist", "build",
    "__pycache__", ".venv", "venv", ".mypy_cache", ".pytest_cache",
}

@dataclass
class FileRecord:
    path: str
    mtime_ns: int
    size: int
    sha256: str

# ---------------------------------------------------------
# 核心索引器逻辑
# ---------------------------------------------------------
class MemoryIndexer:
    def __init__(self, root: Optional[str | Path] = None, db_path: Optional[str | Path] = None, **_: object) -> None:
        # 如果没传入root，使用配置中的默认源目录列表；如果传入root，追加到列表中（允许覆盖）
        if root is None:
            self.source_dirs = DEFAULT_SOURCE_DIRS.copy()
        else:
            # 如果明确传入root，则只用这个root（保持向后兼容）
            self.source_dirs = [Path(root)]
        self.db_path = Path(db_path) if db_path else (WORKSPACE_ROOT / "memory_system" / DEFAULT_DB_NAME)
        # 挂载新心脏
        self.embedding_client = EmbeddingClient()

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = NORMAL")
        return conn

    def build(self, root: Optional[str | Path] = None, **_: object) -> dict:
        if root:
            self.source_dirs = [Path(root)]
        for src_dir in self.source_dirs:
            src_dir.mkdir(parents=True, exist_ok=True)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as conn:
            self._rebuild_schema(conn)
            files_indexed, chunks_indexed = self._index_all_files(conn)
            conn.commit()
        return {
            "status": "rebuilt",
            "schema_version": SCHEMA_VERSION,
            "source_dirs": [str(d) for d in self.source_dirs],
            "db_path": str(self.db_path),
            "files_indexed": files_indexed,
            "chunks_indexed": chunks_indexed,
            "embedding_enabled": self.embedding_client.available,
        }

    def update(self, root: Optional[str | Path] = None, **_: object) -> dict:
        if root:
            self.source_dirs = [Path(root)]
        for src_dir in self.source_dirs:
            src_dir.mkdir(parents=True, exist_ok=True)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as conn:
            if not self._is_schema_compatible(conn):
                result = self.build()
                result["status"] = "rebuilt_from_incompatible_schema"
                result["note"] = "Detected old prototype schema; performed a full rebuild."
                return result

            self._ensure_schema(conn)
            current_files = {record.path: record for record in self._scan_files()}
            indexed_files = self._load_indexed_files(conn)

            removed = sorted(set(indexed_files) - set(current_files))
            added_or_changed = []
            for path, record in current_files.items():
                old = indexed_files.get(path)
                if old is None or old["mtime_ns"] != record.mtime_ns or old["size"] != record.size or old["sha256"] != record.sha256:
                    added_or_changed.append(record)

            removed_chunks = 0
            for rel_path in removed:
                removed_chunks += self._delete_file(conn, rel_path)

            files_indexed = 0
            chunks_indexed = 0
            for record in added_or_changed:
                self._delete_file(conn, record.path)
                chunks_indexed += self._index_file(conn, record)
                files_indexed += 1

            conn.commit()
            return {
                "status": "updated",
                "schema_version": SCHEMA_VERSION,
                "source_dirs": [str(d) for d in self.source_dirs],
                "db_path": str(self.db_path),
                "files_indexed": files_indexed,
                "chunks_indexed": chunks_indexed,
                "files_removed": len(removed),
                "chunks_removed": removed_chunks,
                "embedding_enabled": self.embedding_client.available,
            }

    def _rebuild_schema(self, conn: sqlite3.Connection) -> None:
        for trigger_name in ("chunks_ai", "chunks_ad", "chunks_au"):
            conn.execute(f"DROP TRIGGER IF EXISTS {trigger_name}")
        conn.execute("DROP TABLE IF EXISTS chunks_fts")
        conn.execute("DROP TABLE IF EXISTS chunks")
        conn.execute("DROP TABLE IF EXISTS files")
        self._ensure_schema(conn, force_recreate=False)

    def _ensure_schema(self, conn: sqlite3.Connection, force_recreate: bool = False) -> None:
        if force_recreate or not self._is_schema_compatible(conn, allow_missing=True):
            if force_recreate:
                self._rebuild_schema(conn)
                return
        conn.executescript(
            f"""
            CREATE TABLE IF NOT EXISTS files (
                path TEXT PRIMARY KEY,
                mtime_ns INTEGER NOT NULL,
                size INTEGER NOT NULL,
                sha256 TEXT NOT NULL,
                indexed_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS chunks (
                id INTEGER PRIMARY KEY,
                path TEXT NOT NULL,
                chunk_index INTEGER NOT NULL,
                title TEXT,
                content TEXT NOT NULL,
                normalized_content TEXT NOT NULL,
                content_hash TEXT NOT NULL,
                embedding_json TEXT,
                UNIQUE(path, chunk_index),
                FOREIGN KEY(path) REFERENCES files(path) ON DELETE CASCADE
            );

            CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
                title,
                content,
                normalized_content,
                content='chunks',
                content_rowid='id',
                tokenize='unicode61'
            );

            CREATE TRIGGER IF NOT EXISTS chunks_ai AFTER INSERT ON chunks BEGIN
                INSERT INTO chunks_fts(rowid, title, content, normalized_content)
                VALUES (new.id, COALESCE(new.title, ''), new.content, new.normalized_content);
            END;

            CREATE TRIGGER IF NOT EXISTS chunks_ad AFTER DELETE ON chunks BEGIN
                INSERT INTO chunks_fts(chunks_fts, rowid, title, content, normalized_content)
                VALUES ('delete', old.id, COALESCE(old.title, ''), old.content, old.normalized_content);
            END;

            CREATE TRIGGER IF NOT EXISTS chunks_au AFTER UPDATE ON chunks BEGIN
                INSERT INTO chunks_fts(chunks_fts, rowid, title, content, normalized_content)
                VALUES ('delete', old.id, COALESCE(old.title, ''), old.content, old.normalized_content);
                INSERT INTO chunks_fts(rowid, title, content, normalized_content)
                VALUES (new.id, COALESCE(new.title, ''), new.content, new.normalized_content);
            END;

            CREATE INDEX IF NOT EXISTS idx_chunks_path ON chunks(path);
            CREATE INDEX IF NOT EXISTS idx_chunks_path_chunk_index ON chunks(path, chunk_index);
            """
        )
        conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")

    def _is_schema_compatible(self, conn: sqlite3.Connection, allow_missing: bool = False) -> bool:
        tables = {
            row[0]: row[1]
            for row in conn.execute(
                "SELECT name, sql FROM sqlite_master WHERE type IN ('table', 'trigger')"
            ).fetchall()
        }
        if allow_missing and not tables:
            return True

        required = {"files", "chunks", "chunks_fts", "chunks_ai", "chunks_ad", "chunks_au"}
        if not required.issubset(tables):
            return False

        chunk_columns = {
            row[1]: {"type": row[2], "pk": row[5]}
            for row in conn.execute("PRAGMA table_info(chunks)").fetchall()
        }
        if "id" not in chunk_columns or chunk_columns["id"]["pk"] != 1:
            return False
        if "normalized_content" not in chunk_columns:
            return False

        fts_sql = tables.get("chunks_fts") or ""
        if "content='chunks'" not in fts_sql or "content_rowid='id'" not in fts_sql:
            return False

        user_version = conn.execute("PRAGMA user_version").fetchone()[0]
        return int(user_version or 0) >= SCHEMA_VERSION

    def _scan_files(self) -> Iterator[FileRecord]:
        db_resolved = self.db_path.resolve()
        home = Path.home()
        # 遍历所有源目录，匹配 DEFAULT_TARGETS 模式
        for source_dir in self.source_dirs:
            source_dir = source_dir.resolve()
            for pattern in DEFAULT_TARGETS:
                # 处理 glob 模式
                for path in source_dir.glob(pattern):
                    if not path.is_file():
                        continue
                    if any(part in SKIP_DIRS for part in path.parts):
                        continue
                    if path.resolve() == db_resolved:
                        continue
                    if path.suffix.lower() not in TEXT_EXTENSIONS and path.stat().st_size > 1_000_000:
                        continue
                    try:
                        # 构建唯一路径：源目录相对家目录 + 相对源目录路径，避免不同源目录间冲突
                        src_rel_home = source_dir.relative_to(home).as_posix()
                        file_rel_src = path.relative_to(source_dir).as_posix()
                        full_rel_path = f"{src_rel_home}/{file_rel_src}"
                        if self._should_ignore(file_rel_src):
                            continue
                        stat = path.stat()
                        sha256 = self._sha256(path)
                    except (OSError, ValueError):
                        continue
                    yield FileRecord(full_rel_path, stat.st_mtime_ns, stat.st_size, sha256)

    @staticmethod
    def _should_ignore(rel_path: str) -> bool:
        normalized = rel_path.replace("\\", "/")
        return any(fnmatch(normalized, pattern) for pattern in DEFAULT_IGNORE_GLOBS)

    def _index_all_files(self, conn: sqlite3.Connection) -> tuple[int, int]:
        files_indexed = 0
        chunks_indexed = 0
        for record in self._scan_files():
            chunks_indexed += self._index_file(conn, record)
            files_indexed += 1
        return files_indexed, chunks_indexed

    def _index_file(self, conn: sqlite3.Connection, record: FileRecord) -> int:
        # record.path 已经是相对于 home 的完整路径，直接还原
        home = Path.home()
        abs_path = home / Path(record.path)
        # [FIX] 二次防御，防止读取目录报错
        if not abs_path.exists() or not abs_path.is_file():
            return 0
            
        text = self._read_text(abs_path)
        if not text.strip():
            self._upsert_file_record(conn, record)
            return 0

        title = self._extract_title(record.path, text)
        chunks = self._split_text(text)
        
        # 调用新注入的 embedding_client
        embeddings = self.embedding_client.embed_texts(chunks)
        
        indexed_at = datetime.now(timezone.utc).isoformat()
        self._upsert_file_record(conn, record, indexed_at=indexed_at)

        for chunk_index, content in enumerate(chunks):
            normalized_content = self._normalize_text(content)
            content_hash = hashlib.sha256(content.encode("utf-8", errors="ignore")).hexdigest()
            embedding_json = json.dumps(embeddings[chunk_index]) if chunk_index < len(embeddings) and embeddings[chunk_index] is not None else None
            conn.execute(
                """
                INSERT INTO chunks (
                    path, chunk_index, title, content, normalized_content, content_hash, embedding_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (record.path, chunk_index, title, content, normalized_content, content_hash, embedding_json),
            )
        return len(chunks)

    def _upsert_file_record(self, conn: sqlite3.Connection, record: FileRecord, indexed_at: Optional[str] = None) -> None:
        conn.execute(
            """
            INSERT INTO files (path, mtime_ns, size, sha256, indexed_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(path) DO UPDATE SET
                mtime_ns = excluded.mtime_ns,
                size = excluded.size,
                sha256 = excluded.sha256,
                indexed_at = excluded.indexed_at
            """,
            (
                record.path,
                record.mtime_ns,
                record.size,
                record.sha256,
                indexed_at or datetime.now(timezone.utc).isoformat(),
            ),
        )

    def _load_indexed_files(self, conn: sqlite3.Connection) -> dict[str, sqlite3.Row]:
        return {
            row["path"]: row
            for row in conn.execute("SELECT path, mtime_ns, size, sha256 FROM files").fetchall()
        }

    def _delete_file(self, conn: sqlite3.Connection, rel_path: str) -> int:
        chunk_count_row = conn.execute("SELECT COUNT(*) FROM chunks WHERE path = ?", (rel_path,)).fetchone()
        chunk_count = int(chunk_count_row[0]) if chunk_count_row else 0
        conn.execute("DELETE FROM chunks WHERE path = ?", (rel_path,))
        conn.execute("DELETE FROM files WHERE path = ?", (rel_path,))
        return chunk_count

    @staticmethod
    def _sha256(path: Path) -> str:
        h = hashlib.sha256()
        with path.open("rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()

    @staticmethod
    def _read_text(path: Path) -> str:
        # [NEW] 兼容老机器上的 ANSI 乱码
        for encoding in ("utf-8", "utf-8-sig", "gbk", "gb18030", "latin-1"):
            try:
                return path.read_text(encoding=encoding)
            except Exception:
                continue
        try:
            return path.read_bytes().decode("utf-8", errors="ignore")
        except Exception:
            return ""

    @staticmethod
    def _extract_title(rel_path: str, text: str) -> str:
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith("#"):
                return stripped.lstrip("# ").strip() or Path(rel_path).stem
            return stripped[:120]
        return Path(rel_path).stem

    @classmethod
    def _normalize_text(cls, text: str) -> str:
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        text = re.sub(r"\s+", " ", text)
        return text.strip().lower()

    def _split_text(self, text: str, max_chars: int = 1200, overlap: int = 150, max_chunks: int = 20) -> list[str]:
        """
        智能文本分块，支持更大文件的处理
        1. 尽量按段落分块
        2. 限制总块数
        3. 保留关键上下文
        """
        # 预处理：移除过多的空白和换行
        text = re.sub(r'\n{3,}', '\n\n', text)

        # 按段落和标题分块
        paragraphs = re.split(r'\n\s*\n+|\n(?=#+\s)', text)
        paragraphs = [p.strip() for p in paragraphs if p.strip()]

        if not paragraphs:
            return [text.strip()] if text.strip() else []

        chunks: list[str] = []
        current = ""

        for para in paragraphs:
            # 标题优先处理
            if para.startswith('#'):
                if current:
                    chunks.append(current.strip())
                    current = ""
                chunks.append(para)
                continue

            candidate = para if not current else current + "\n\n" + para

            if len(candidate) <= max_chars:
                current = candidate
                continue

            # 如果当前块过长，进行智能截断
            if current:
                chunks.append(current.strip())

            # 处理长段落
            if len(para) > max_chars:
                # 分割长段落，保留一些连续性
                start = 0
                while start < len(para):
                    piece = para[start : start + max_chars]
                    chunks.append(piece.strip())

                    # 限制总块数
                    if len(chunks) >= max_chunks:
                        break

                    start += max_chars - overlap
                current = ""
            else:
                current = para

        # 添加最后剩余的内容
        if current.strip() and len(chunks) < max_chunks:
            chunks.append(current.strip())

        # 如果块数过多，只保留开头、中间和结尾
        if len(chunks) > max_chunks:
            mid_start = len(chunks) // 2 - max_chunks // 4
            chunks = (
                chunks[:max_chunks//3] +  # 开头部分
                chunks[mid_start:mid_start + max_chunks//3] +  # 中间部分
                chunks[-max_chunks//3:]  # 结尾部分
            )

        return [chunk for chunk in chunks if chunk.strip()]