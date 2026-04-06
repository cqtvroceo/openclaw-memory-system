# Echo Memory System 3.0 - 本地 AI 长期记忆系统 / Local AI Long-Term Memory System

## 项目介绍 / Project Introduction

Echo Memory System 3.0 是一个创新的本地向量记忆系统，专为 AI Agent 设计，解决了传统 AI 对话中「记忆」的关键挑战。

Echo Memory System 3.0 is an innovative local vector memory system designed for AI Agents, addressing the critical memory challenges in traditional AI conversations.

### 核心特性 / Core Features

- 🚀 零 API 成本 / Zero API Cost
- 🔍 混合检索引擎 / Hybrid Retrieval Engine
- 💾 本地向量存储 / Local Vector Storage
- ⚡ 高效上下文压缩 / Efficient Context Compression

## 架构图 / Architecture Diagram

```
┌─────────────────────────────────────────────────┐
│                  Query 输入 / Input             │
└──────────────────┬──────────────────────────────┘
                   │
         ┌─────────▼──────────┐
         │   混合检索引擎      │
         │   Hybrid Retrieval │
         │                    │
         │  ┌──────────────┐  │
         │  │ BM25 关键词   │  │
         │  │ Keyword Search│  │
         │  └──────┬───────┘  │
         │         │          │
         │  ┌──────▼───────┐  │
         │  │ 语义向量检索  │  │
         │  │ Semantic Search││
         │  └──────┬───────┘  │
         │         │          │
         │  ┌──────▼───────┐  │
         │  │  RRF 融合排序  │  │
         │  │ RRF Fusion    │  │
         │  └──────┬───────┘  │
         │         │          │
         │  ┌──────▼───────┐  │
         │  │ 时间衰减 Boost │  │
         │  │ Time Decay   │  │
         │  └──────┬───────┘  │
         └─────────┼──────────┘
                   │
         ┌─────────▼──────────┐
         │  Context Pack 压缩  │
         │  Context Compression│
         └─────────┬──────────┘
                   │
         ┌─────────▼──────────┐
         │   注入 Prompt      │
         │   Inject Prompt   │
         └────────────────────┘
```

## 快速开始 / Quick Start

### 安装依赖 / Install Dependencies

```bash
# 克隆仓库 / Clone Repository
git clone https://github.com/yourusername/echo-memory-system.git

# 安装依赖 / Install Dependencies
pip install -r requirements.txt
```

### 构建索引 / Build Index

```bash
# 构建记忆索引 / Build Memory Index
python -m memory_system.cli build --json
```

### 使用示例 / Usage Examples

```bash
# 搜索记忆 / Search Memories
python -m memory_system.cli search "你的查询" --json

# 压缩上下文 / Compress Context
python -m memory_system.cli pack "你的查询" --json
```

## 配置说明 / Configuration

### 嵌入服务 / Embedding Service

```python
# 配置本地嵌入服务 / Configure Local Embedding Service
DEFAULT_EMBED_BASE_URL = "http://192.168.6.156:8080/v1"
DEFAULT_EMBED_MODEL = "nomic-embed-text-v1.5.f16.gguf"
```

## 技术栈 / Tech Stack

| 组件 / Component | 选型 / Choice | 理由 / Reason |
|-----------------|--------------|--------------|
| 存储 / Storage | SQLite + FTS5 | 零依赖，单文件，内置全文搜索 / Zero dependencies, single file, built-in full-text search |
| 嵌入 / Embedding | nomic-embed-text (本地) / Local | 零 API 成本，768 维 / Zero API cost, 768 dimensions |
| 关键词搜索 / Keyword Search | BM25 (FTS5) | 精确匹配，速度快 / Precise matching, fast |
| 语义搜索 / Semantic Search | Cosine 相似度 / Similarity | 理解意图，覆盖同义词 / Understand intent, cover synonyms |
| 结果融合 / Result Fusion | RRF (k=60) | 不需要调参，通用性强 / No parameter tuning, high universality |

## 性能对比 / Performance Comparison

| 指标 / Metric | 优化前 / Before (1.0) | 优化后 / After (3.0) |
|--------------|----------------------|---------------------|
| 检索精准度 / Retrieval Accuracy | 看运气 / Luck-based | RRF 融合，显著提升 / RRF Fusion, Significantly Improved |
| Token 消耗 / Token Consumption | 全文注入，成本高 / Full text, High Cost | 降低 80%+ / Reduced by 80%+ |
| 响应速度 / Response Speed | 历史越长越慢 / Slower with More History | 固定注入量，稳定 / Stable Injection |

## 贡献 / Contribution

欢迎提交 Issue 和 Pull Request！
Welcome to submit Issues and Pull Requests!

## 许可证 / License

[选择并添加适当的许可证]
[Choose and add an appropriate license]

## 联系方式 / Contact

[添加项目作者或维护者的联系信息]
[Add project author or maintainer contact information]