from pathlib import Path
WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB_PATH = WORKSPACE_ROOT / "memory_system" / "memory_index.sqlite3"
DEFAULT_TARGETS = [
 "*.md",
 "memory/*.md",
]

DEFAULT_SOURCE_DIRS = [
 Path.home() / ".openclaw" / "workspace",
 Path.home() / ".openclaw" / "workspace-coder",
 Path.home() / ".openclaw" / "workspace-researcher",
 Path.home() / ".openclaw" / "workspace-supervisor",
 Path.home() / ".openclaw" / "workspace-writer",
]
DEFAULT_IGNORE_GLOBS = [
    # ���ݿ��ļ�
    "*.sqlite",
    "*.sqlite3",
    "*.sqlite-wal",
    "*.sqlite-shm",
    "*.sqlite3-wal",
    "*.sqlite3-shm",
    # ��ʱ��Ƭ�ļ�
    "*_py_*.txt",
    "*_md_*.txt",
    "_*_snips.txt",
    "_snippets/*.txt",
    # memory_system ����Ŀ¼��ȫ�ų�
    "memory_system/*",
    # �����ļ�
    "*.py",
    "*.js",
    "*.ts",
    "*.tsx",
    "*.jsx",
    "*.json",
    "*.jsonl",
    "*.yaml",
    "*.yml",
    "*.toml",
    "*.ini",
    "*.cfg",
    "*.sh",
    "*.ps1",
    "*.bat",
    "*.cmd",
    "*.html",
    "*.htm",
    "*.css",
    "*.sql",
]
DEFAULT_EMBED_BASE_URL = "http://192.168.6.156:8080/v1"
DEFAULT_EMBED_MODEL = "nomic-embed-text-v1.5.f16.gguf"
DEFAULT_CHUNK_SIZE = 1200
DEFAULT_CHUNK_OVERLAP = 150