# 0002 - 为什么选 SQLite

**Date**: 2026-05-09
**Status**: Accepted

## 背景

需要存的数据：
- sources / jobs / matches / pushes / feedback 共 5 张表
- 预估一年内数据量 < 10 万行
- 需要在 GitHub Actions 跑，希望 state 能随 commit 持久化

## 决策

**SQLite 单文件**，通过 SQLAlchemy 访问。

## 取舍

| 方案 | 优 | 劣 |
|---|---|---|
| SQLite | 零运维 / 随仓库 commit / 本地 grep 友好 | 并发弱（本项目单进程，不是问题） |
| Postgres (云) | 并发强 / 有 JSON index | 多花 ¥50/月 / 要管账号 / 本地测试麻烦 |
| DuckDB | 分析强 | 生态不如 sqlite 成熟 |
| JSON 文件 | 最轻 | 5 张关联表用 JSON 难受 |

**决定性因素**：本项目就是个人级工具，没有并发需求，SQLite 的"单文件 = 状态"特性让 GitHub Actions 持久化几乎 free：

```yaml
- run: uv run job-radar run
- name: commit state
  run: |
    git add data/radar.sqlite
    git commit -m "radar state" || true
    git push
```

## 后果

+ 简单得过分
+ 本地 `sqlite3 data/radar.sqlite` 随时查
- 数据量超 50MB 后 commit 会显眼（届时迁 git LFS 或换 Postgres）

