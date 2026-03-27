# MailWise

[![CI](https://github.com/PetrGuan/MailWise/actions/workflows/ci.yml/badge.svg)](https://github.com/PetrGuan/MailWise/actions/workflows/ci.yml)
[![PyPI version](https://badge.fury.io/py/mailwise.svg)](https://pypi.org/project/mailwise/)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://python.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

[English](README.md) | [中文](README.zh-CN.md)

将邮件线程转化为可搜索的知识库。解析 EML 文件，使用向量嵌入建立索引，通过 RAG 学习团队资深工程师分析问题的方式。

## 功能介绍

MailWise 读取 `.eml` 文件（从 Outlook、Thunderbird 等导出），将邮件线程拆分为单独的回复，并构建语义搜索索引。你可以：

- **搜索** — 使用自然语言查找相似的历史问题
- **分析** — 通过 RAG 让 Claude 阅读专家工程师解决类似问题的过程，并给出建议
- **标记专家工程师** — 专家的回复在搜索结果中获得加权提升，并在输出中高亮显示

## 为什么需要它

如果你的团队通过邮件处理 Bug 和事故，多年积累的经验知识就埋藏在邮件线程中。MailWise 让这些知识变得可搜索、可利用。

## 快速开始

### 前置要求

- Python 3.10+
- [Claude Code](https://claude.ai/code)（用于 `analyze` 命令 — 使用你已有的认证，无需额外 API 密钥）

### 安装

从 PyPI 安装：

```bash
pip install mailwise
```

或从源码安装：

```bash
git clone https://github.com/PetrGuan/MailWise.git
cd MailWise
pip install -e .
```

### 配置

最简单的方式：

```bash
mailwise init
```

这会引导你设置 EML 目录、添加专家工程师，并验证配置。

或手动配置：

```bash
cp config.example.yaml config.yaml
```

编辑 `config.yaml`：

```yaml
eml_directory: /path/to/your/eml/files
database: data/index.db
markdown_directory: markdown
embedding_model: all-MiniLM-L6-v2
expert_boost: 1.5

experts:
  - email: senior.dev@company.com
    name: Jane Doe
```

### 使用方法

```bash
# 索引邮件（增量处理 — 只处理新增或修改的文件）
mailwise index

# 搜索相似的历史问题
mailwise search "文件夹迁移后同步失败"

# 搜索并显示预览
mailwise search "日历不更新" --show-body

# 只显示专家工程师的回复
mailwise search "删除的邮件又出现了" --expert-only

# 深度分析 — Claude 基于相似的专家线程进行推理
mailwise analyze "用户反馈将邮件移动到本地文件夹后，邮件不断重新出现在收件箱中"

# 查看特定邮件线程的完整 Markdown
mailwise show 42

# 查看索引统计
mailwise stats
```

### 管理专家工程师

```bash
# 添加专家
mailwise experts add engineer@company.com --name "Jane Doe"

# 列出所有专家
mailwise experts list

# 移除专家
mailwise experts remove engineer@company.com
```

## 工作原理

```
EML 文件 → 解析器 → Markdown + 向量嵌入 → SQLite 索引
                                                  ↓
                            查询 → 语义搜索 → 最相似的结果
                                                      ↓
                                     Claude (RAG) → 基于专家经验的分析
```

1. **解析**：并行解析 EML 文件，按 Outlook 风格的 `From:/Sent:` 分隔符拆分线程
2. **清洗**：还原 Microsoft SafeLinks 链接，清除 mailto 标记
3. **Markdown**：每个线程生成结构化的 Markdown 文件，专家回复标记为 `[Expert]`
4. **嵌入**：使用 `all-MiniLM-L6-v2` 对每条回复生成向量（本地运行，无需 API 调用）
5. **索引**：向量和元数据存储在 SQLite 中，支持快速检索
6. **搜索**：余弦相似度 + 专家分数加权，找到最相关的历史问题
7. **分析**：将最相似的结果发送给 Claude（通过 Claude Code CLI），系统提示词引导其关注专家的推理模式

## 性能

专为大型邮箱设计（25,000+ 封邮件，16GB+）：

| 操作 | 性能 |
|---|---|
| 增量检查（无变更） | 25K 文件约 2-3 秒（基于文件状态，无需读取文件） |
| 全量索引 | 约 5-10 分钟（并行解析 + 批量嵌入） |
| 搜索查询 | <100 毫秒（单次矩阵乘法，覆盖 100K+ 向量） |
| RAG 分析 | 约 10-20 秒（检索 + Claude 响应） |

核心优化：
- **两阶段变更检测**：先检查 mtime+size，再进行 SHA256 哈希
- **并行 EML 解析**：多进程，可配置工作线程数
- **批量嵌入**：预计算偏移数组，避免 O(n²) 查找
- **优化搜索**：仅加载嵌入 BLOB 到连续 numpy 数组；仅对 top-k 结果获取元数据
- **SQLite 调优**：WAL 日志、64MB 缓存、256MB mmap、批量插入

## 项目结构

```
src/email_issue_indexer/
├── cli.py          # 基于 Click 的命令行界面
├── parser.py       # EML 解析 + 线程拆分（支持并行）
├── markdown.py     # Markdown 转换，带专家标签
├── safelinks.py    # Microsoft SafeLinks 链接还原
├── embeddings.py   # sentence-transformers 嵌入 + 向量搜索
├── store.py        # SQLite 存储层（性能调优）
├── indexer.py      # 并行批量编排器，带进度追踪
├── search.py       # 优化的相似度搜索，带专家加权
└── rag.py          # RAG 层，使用 Claude Code CLI
```

## 隐私保护

所有处理均在本地完成：
- 向量嵌入在你的机器上运行（索引过程不向任何 API 发送数据）
- 邮件内容存储在本地 SQLite 数据库和 Markdown 文件中
- `analyze` 命令会将相关线程摘录发送给 Claude — 与在 Claude Code 中对话相同

`config.yaml`、`emails/`、`data/` 和 `markdown/` 目录默认被 gitignore。只有 `config.example.yaml`（不含真实数据）会被提交。预提交钩子（`scripts/install-hooks.sh`）会扫描意外的个人信息泄露。

## 使用技巧

- **搜索时**：使用自然语言描述，越具体越好。包含错误代码、API 名称、平台信息（Mac/Windows/iOS）能显著提升匹配质量。
- **分析时**：粘贴完整的 Bug 报告内容，而不仅仅是标题。更多上下文 = 更好的匹配结果。
- **专家配置**：添加你团队中最有经验的工程师，他们的回复会在搜索中获得加权提升，Claude 分析时也会格外关注他们的推理过程。

## 许可证

MIT
