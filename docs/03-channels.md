# 03 - 推送渠道

> 什么时机用什么渠道推到什么地方。M1 纯邮件，后续渐进加。

---

## 分档策略

| 分数 | 档位 | 渠道 | 频率 |
|---|---|---|---|
| ≥ 90 | 🔴 首投 | 邮件单发（subject 含 🔴） + 日报置顶 | 实时 |
| 75-89 | 🟡 精投 | 邮件日报 | 每日 09:00 |
| 60-74 | 🟢 候选 | 日报 "More" 区折叠 + 周报 | 每日批量 |
| < 60 | 丢弃 | 只留 SQLite 记录 | — |

---

## M1 — Email First（Gmail SMTP）

**一期就这一个渠道**，其他不做。

### 为什么纯邮件

1. 用户主张"哪个简单用哪个"—— SMTP 最简单
2. 邮箱是被动接收，不用装新 App
3. Gmail 自带搜索、归档、过滤器，本身就是个看板
4. 邮件天然有链接，feedback 用 "click to vote" 就行，不用自建 Bot

### Gmail SMTP 配置

```
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=you@example.com
SMTP_PASS=<App Password, 非账号密码>
SMTP_FROM=you@example.com
SMTP_TO=you@example.com
```

App Password 去 https://myaccount.google.com/apppasswords 生成（16 位字符）。Gmail SMTP 每天 500 封上限，够用 100 倍。

### 两种邮件

**A. 实时邮件**（≥ 90 分触发）

```
Subject: 🔴 [92] OKX - Senior AI Agent Engineer (Singapore/Remote)

--- HTML body ---
Score: 92 / 100
  • tech_stack: 95
  • scenario: 95
  • seniority: 85
  • company_fit: 90  (remote Asia 加权)

Why: 命中 LangGraph + MCP + Crypto 三项稀缺组合
Risks: 要求 TS 前端经验

Suggested resume: V3 (Crypto × AI)
Cover letter angle: 强调自研 AI Workflow + CoinW Meme 平台 lead 经验

[Apply] [👍 Want] [👎 Skip] [⏸️ Already applied]

Source: okx-lever | Posted: 2026-05-08
```

**B. 日报邮件**（每日 09:00）

```
Subject: 🎯 Job Radar Daily — 2026-05-09 (3 high, 7 medium)

🔴 High Priority
  1. [92] OKX - Senior AI Agent Engineer (Remote)
  2. [91] Chainlink Labs - Staff AI Eng (Remote)
  3. [90] LangChain - Senior AI Engineer (US Remote)

🟡 Medium
  4. [84] Coinbase - AI/ML Platform (Remote US)
  ...

🟢 Candidates (折叠)
  ...

📊 Stats
  Crawled: 87 | Passed filter: 23 | Scored: 12
  Your last week: 5 👍 / 2 applied / 1 👎

🔍 Trending keywords
  "MCP server" +40%, "Agent evaluation" +25%
```

**反馈链接（M3 前先不启用真实 webhook）**

M1 邮件里暂时只放 `[Apply]` 链接，反馈按钮留 placeholder。M3 起上一个轻量 FastAPI endpoint（或 Vercel function），点击时写 SQLite / Turso。

---

## M2 — GitHub Issue（顺手加）

每条 JD 一个 issue，当持久看板和"面试准备卡片"用。Labels：
- `track:crypto-ai` / `track:ai-app-arch` / `track:ai-infra`
- `priority:high/med/low`
- `status:new` → 手动改 `status:applied` / `status:rejected`
- `company:okx` / `company:binance` ...

仓库私有，暴露目标公司不敏感。

## M3 — Telegram Bot（可选）

如果 M2 前你觉得"邮件通知有延迟 + 没 iOS push 想要弹窗"，就加。
- 实时推送 ≥ 90 分 JD
- inline keyboard 按钮反馈
- `/today` / `/trend` / `/pause 7d`

## M4+ — 飞书 / 企业微信 webhook

留抽象接口，不默认实现。

---

## 时机与频控

### 频控

- 同一 fingerprint 3 天内不重推
- JD 更新（薪资/地点变化）只重推一次
- 单日日报 JD 上限：≥ 90 档不限，75-89 档 ≤ 15 条，超出压到明日

### 静默时段

- 实时邮件在北京时间 23:00-08:00 不发（日报正常 09:00 发）
- CLI `job-radar pause 7d` 全部静默

---

## 抽象接口

```python
class ChannelMessage(BaseModel):
    job: Job
    score: Score
    tier: Literal["high", "med", "low"]
    reason_brief: str
    apply_url: str
    feedback_token: str

class Channel(Protocol):
    name: str
    def send(self, msg: ChannelMessage) -> SendResult: ...
    def send_digest(self, messages: list[ChannelMessage], kind: Literal["daily", "weekly"]) -> SendResult: ...
```

每渠道一个文件，独立单测（mock HTTP）。失败不阻塞 pipeline，写入 `outbox` 表下轮重试。
