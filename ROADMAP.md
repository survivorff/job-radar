# ROADMAP

> 从"能收到第一封邮件"到"可托管在 GitHub Actions 自跑"的 6 个里程碑。

---

## M0 — 设计与骨架（已完成）

- 4 份核心设计文档 + 3 条 ADR
- 仓库骨架 + profile 示例
- 目标池：种子 + 动态发现（不固定）

## M1 — 能收到第一封邮件（已完成）

- [x] `sources/lever.py`（Binance 等）
- [x] `sources/greenhouse.py`（OKX / Binance / Bybit / Gemini / Consensys / BitGo / Ripple / Anthropic / Stripe）
- [x] `sources/ashby.py`（LangChain / OpenAI / Kraken / Cohere / Mem0 / Blockstream / Solana Labs）
- [x] `pipeline/hard_filter.py`
- [x] `pipeline/heuristic_scorer.py`（含 remote 加权）
- [x] `channels/email_smtp.py`（Gmail SMTP + 3 次重试）
- [x] CLI: `run` / `digest --daily` / `test-email` / `stats`
- [x] 本地 cron 示例（docs/GET-STARTED.md）

## M1.5 — 排版 + Skill 包装（已完成）

- [x] 邮件模板双语（EN + ZH）
- [x] 维度进度条（tech_stack / scenario / seniority / company_fit）
- [x] 列出**命中的关键词**作为证据
- [x] 每条 JD 一段 bilingual explanation（"为什么命中 / 需要验证什么"）
- [x] SMTP 3 次重试（Gmail 偶尔掉连接）
- [x] Claude Skill 包装 `skills/job-radar/`：SKILL.md + 4 个脚本（show_top / query / explain / probe_ats）

## M2 — 打分精度达标（~1 周）

- [ ] `pipeline/embed_recall.py`（BGE-M3 本地 + cosine 阈值）
- [ ] `pipeline/llm_scorer.py`（DeepSeek 结构化输出 + 预算熔断 + remote 加权）
- [ ] `channels/github_issue.py`（顺手加，当看板用，一条 JD 一个 issue）
- [ ] Eval：人工标 30 条金标，校准阈值

**验收**：日报里 75+ 档的 JD，我点 "想投/已投" 的比例 ≥ 60%。

## M3 — 交互反馈（~1 周）

- [ ] `channels/telegram.py`（可选，≥90 分实时推 + inline 按钮）
- [ ] `pipeline/feedback.py`（邮件里加 3 个反馈链接 → webhook → SQLite）
- [ ] 周报：每周日 21:00

**验收**：能在邮件或 TG 点反馈，状态写回数据库并影响下周推送。

## M4 — 扩展池 + 自动调参（~2 周）

- [ ] 数据源扩展：`cryptojobslist` / `remote3.co` / `YC` / `HN Who is hiring`
- [ ] 反馈闭环自动调硬规则阈值
- [ ] 关键词趋势周报（顺便喂 `market-jd-analysis.md`）

**验收**：每周至少推出 1 条 target list 外但高分匹配的"意外之喜"（大概率 remote crypto 岗）。

## M5 — GitHub Actions 托管（~1 周）

- [ ] `.github/workflows/radar.yml`（每小时 cron）
- [ ] LLM Key / SMTP Pass 走 Secrets
- [ ] SQLite 文件 commit 回仓库做 state 持久化

**验收**：电脑关机也能每小时跑。

## M6 — 后续再议

原开源计划暂缓，按用户决定。

---

## 刹车条件

- M1 两周内还没跑通 → 砍到只保留 2 个 Lever + 1 个聚合站
- 连续 2 周没推出 75+ 的 JD → 检查硬规则是不是过严（尤其 location 和 keyword）
- LLM 日均成本 > ¥3 → 查哪一步泄漏，大概率是去重坏了
