# 0001 - 为什么选 Python + LiteLLM

**Date**: 2026-05-09
**Status**: Accepted

## 背景

本项目需要：
1. HTTP 抓取 + HTML 解析
2. 本地跑 Embedding
3. 调多个 LLM API
4. 写 CLI + 定时任务

可选技术栈：Python / Node.js / Go。

## 决策

**Python 3.11 + uv + LiteLLM**。

## 取舍

| 维度 | Python | Node.js | Go |
|---|---|---|---|
| AI 生态（fastembed/langchain/litellm） | ★★★★★ | ★★★ | ★★ |
| HTTP + 解析库 | ★★★★ | ★★★★ | ★★★★ |
| 调度（APScheduler） | ★★★★ | ★★★ | ★★★ |
| 与 showcase-a 栈一致性 | ★★★★★ | ★ | ★ |
| 冷启动 / 内存 | ★★ | ★★★ | ★★★★★ |

**决定性因素**：showcase-a 已经用 Python + LiteLLM，本项目完全复用其 `llm.py` / `trace.py` / Makefile 结构，节省至少 1 周重复工作。

## 后果

+ 与 showcase-a 双向复用
+ AI 工具链支持最好
- 打包分发不如 Go（但本项目不面向外部分发，M6 开源时走 Docker 即可）

## 相关

- showcase-a 的 ADR 0001（why LangGraph）风格参考
