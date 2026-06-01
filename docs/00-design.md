# 00 - 核心设计

> 整个项目的思路总览。其他文档是对本文的展开。

---

## 1. 问题定义

我的求职场景有四个特点：

1. **目标池是横跨的**：Crypto × AI（OKX/Binance/Chainlink 等海外 remote）+ 大厂 AI（字节/阿里/腾讯）+ AI Infra（Moonshot/DeepSeek）+ 出海（LangChain/YC）。没有哪一个招聘平台能全覆盖
2. **关键词匹配不够用**：JD 里 "AI Engineer" 一抓一大把，但我只匹配 Agent / RAG / MCP / Crypto×AI 稀缺组合
3. **我已经有清晰的画像**：resume + job-targets.md + market-jd-analysis.md 三份文档已足够生成 "Frank Profile"
4. **推送时机敏感**：海外 remote 岗经常几天就关，需要近实时发现

常规招聘订阅解决不了前三点。本工具是针对这个画像定制的**个人 JD 雷达**。

### 特殊强调：海外 Remote Crypto × AI 优先

根据 `career-reset-2026-05.md` 的 ROI 排序，**A 类 Crypto × AI 岗是首推**，其中**海外 / remote** 又是首选。

因此：
- `tracks.crypto_ai` 标记 `prefer_remote_overseas: true`，Stage 3 LLM 打分时 remote/海外 JD 的 `company_fit` 维度 +10-15 分
- 数据源 L1 优先做 Lever / Greenhouse / Ashby（海外 crypto 公司 90% 用这三家）
- L2 聚合站 web3.career 和 cryptojobslist 当"动态发现"入口，专门挖种子清单外的 remote crypto 岗

---

## 2. 核心循环

```
       ┌───────────┐
       │  Sources  │   L1 官方 ATS (Lever/Greenhouse/Ashby) → 海外 crypto 主力
       │           │   L2 聚合站 (web3.career / ai-jobs.net) → 动态发现
       │           │   L3 综合站 (LinkedIn via Gmail 转发) → 被动补充
       │           │   L4 被动订阅 (TG/Discord/公众号)
       └─────┬─────┘
             │ raw_jobs
             ▼
       ┌───────────┐
       │Hard Filter│   关键词 / 职级 / 地点 → 扔掉 80%
       │           │   (薪资门槛已移除，不硬过滤)
       └─────┬─────┘
             │
             ▼
       ┌───────────┐
       │Embed Recall│  BGE-M3 + cosine  → 再扔掉 75%
       └─────┬─────┘
             │
             ▼
       ┌───────────┐
       │ LLM Scorer │  DeepSeek 结构化打分 + remote 加权
       └─────┬─────┘
             │
        ┌────┴────┬─────────┐
        ▼         ▼         ▼
      ≥90      75-89     60-74
   邮件实时   邮件日报   日报折叠
        │         │         │
        ▼         ▼         ▼
       ┌───────────────────┐
       │  反馈回写  (M3+)   │ → 校准阈值 / few-shot
       └───────────────────┘
```

---

## 3. 四大问题的答案

### 3.1 数据源

按"信号质量 × 抓取成本"分四层。**目标公司池不固定**：种子清单 16 家 + L2 聚合站持续发现。[详见 01-sources.md](./01-sources.md)。

| 层 | 代表 | 抓取 | 优先级 |
|---|---|---|---|
| L1 官方 ATS | OKX/Binance/Chainlink/Kraken/Coinbase (Lever/Greenhouse/Ashby JSON) | 公开 JSON API | P0 |
| L2 聚合站 | web3.career / cryptojobslist / ai-jobs.net / YC / HN | RSS/JSON/HTML | P0 |
| L3 综合站 | LinkedIn | Job Alert 邮件转发 + IMAP | P2 |
| L4 被动订阅 | Telegram 群 / Discord / X KOL | RSSHub/Bot | P2 |

### 3.2 匹配算法

三段流水线，从便宜到贵，90% JD 在前两段就扔掉。[详见 02-matching.md](./02-matching.md)。

- Stage 1 硬规则：关键词 / 职级 / 地点（**无薪资门槛**）
- Stage 2 向量召回：profile embedding × JD embedding（近免费）
- Stage 3 LLM 精评：结构化输出四维分数 + 理由 + 建议简历版本，**remote/海外 crypto 岗加权**（~¥0.002/条）

### 3.3 推送渠道

**M1 纯邮件**（Gmail SMTP 到 `you@example.com`）。后续按需加 GH Issue / Telegram。[详见 03-channels.md](./03-channels.md)。

| 档位 | 分数 | M1 渠道 |
|---|---|---|
| 首投 | ≥90 | 单独邮件（subject 含 🔴）+ 日报置顶 |
| 精投 | 75-89 | 日报主体 |
| 候选 | 60-74 | 日报折叠 + 周报 |

### 3.4 其他

合规、隐私、运维、成本、失败处理，详见 [05-ops.md](./05-ops.md)。

---

## 4. 技术选型一句话

和 [showcase-a-onchain-agent](../../frank-ai-career/showcases/a-onchain-agent) 同一套栈：

- Python 3.11 + uv + pydantic + typer + loguru
- httpx（默认）+ playwright（仅必要站点）
- SQLAlchemy + SQLite
- fastembed（BGE-M3）+ LiteLLM（DeepSeek 主力）
- APScheduler（一期）→ GitHub Actions（M5）

---

## 5. 非目标（明确不做）

- ❌ 不做通用招聘聚合站（不面向其他人）
- ❌ 不做一键投递（投递前一定要人审 + 定制 cover letter）
- ❌ 不爬需要登录的页面（合规风险）
- ❌ 不做可视化大屏（邮件 + 日报 + 看板够了）
- ❌ 不做跨语言 JD 翻译（英文 JD 直推）
- ❌ 不对薪资做硬过滤（让 LLM 综合判断）

---

## 6. 成功标准

M3 结束时：

1. 每周自动推出 5-10 条匹配 ≥ 75 的 JD，**至少 60% 是海外 remote**
2. 我点 "想投" 的比例 ≥ 60%
3. 出现至少 1 条我自己原本没注意到但高分的 JD（大概率来自 web3.career 动态发现）
4. LLM 成本 ≤ ¥30/月
