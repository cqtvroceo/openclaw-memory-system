---
name: memory-system
description: 本地向量记忆系统（回声方案）- 混合全文搜索+向量检索，支持增量更新，利用本地嵌入模型实现低成本高效记忆检索。用于在对话中自动检索相关历史记忆，精简上下文节约 token 成本。
---

# 本地向量记忆系统 (Echo Memory System)

实现了"回声方案"的核心记忆检索系统，支持：
- **混合检索**: 全文搜索 (BM25) + 语义向量检索
- **增量更新**: 支持增量索引，无需每次全量重建
- **本地优先**: 对接本地 embedding 服务（如 Ollama/LLama.cpp），降低成本
- **SQLite 存储**: 简单可靠，无需额外数据库

## 当你需要使用本技能：

> **使用前请确保 Python 能找到技能目录：
> ```bash
> # 添加技能目录到 PYTHONPATH (可在启动时自动执行)
> $env:PYTHONPATH = "$env:PYTHONPATH;$env:USERPROFILE\.agents\skills
> ```

1. **构建/重建全文索引和向量索引**:
```bash
python -m memory-system.memory_system.cli build --json
```
*(运行在工作区根目录)*

2. **搜索相关记忆**:
```bash
python -m memory-system.memory_system.cli search "你的查询词" --json
```

3. **打包检索结果，准备送入上下文**:
```bash
python -m memory-system.memory_system.cli pack "你的查询词" --json
```
`pack` 命令会自动做检索+结果拼接+token 压缩，直接输出可用的上下文。

4. **在技能目录内直接运行**:
```bash
cd memory-system/memory_system
python cli.py search "你的查询词" --json
```

## 核心组件

- **嵌入模型**: 本地运行 nomic-embed-text-v1.5，通过 `http://192.168.6.156:8080/v1` 提供 API
- **存储**: SQLite 内置全文索引 + 向量存储
- **检索**: 混合关键词+语义排序

## 目录结构

```
memory-system/                # 技能包
├── SKILL.md                 # 本文件
└── memory_system/           # Python 包（可作为模块导入
    ├── cli.py               # 命令行入口
    ├── config.py            # 配置
    ├── embeddings.py        # 嵌入调用
    ├── indexer.py          # 索引构建/更新
    ├── searcher.py          # 检索逻辑
    ├── workflow.py          # 工作流封装
    ├── utils.py             # 工具函数
    ├── test_smoke.py        # 冒烟测试
    └── ...
```

## 配置

修改 `memory-system/memory_system/config.py` 调整：
- 嵌入服务地址
- 数据库路径
- 检索结果数量
- 混合排序权重

## 测试

运行冒烟测试验证系统正常工作：
```bash
cd memory-system/memory_system
python test_smoke.py
```
