# 01 - 数据源矩阵

> 去哪里找 JD。海外 remote crypto 岗优先。

---

## 目标池策略：种子 + 动态发现

目标公司**不固定**。有两层：

1. **种子清单** = `frank-ai-career/interview/job-targets.md` 里列的 16 家。这些是"一定要盯"的
2. **动态发现** = L2 聚合站（web3.career / ai-jobs.net / YC）持续扫描，打分 ≥ 80 的公司自动加入"关注池"，下轮巡逻也带上

每 2 周 `make refresh-targets` 命令合并新发现的公司到 `profile/watchlist.yaml`，人工 review 一次。

---

## L1 - 官方 ATS（P0，首批实现）

**海外 crypto 公司绝大多数用 Lever 或 Greenhouse**，数据干净、合规、有公开 JSON API。**优先实现这层**。

### Lever 系（写一个 adapter 吃下全部）

```
GET https://api.lever.co/v0/postings/{slug}?mode=json&location=Remote
```

| 公司 | slug | 备注 |
|---|---|---|
| OKX | okx | A1/A2/A5 目标岗 |
| Binance | binance | A3/A4 |
| Chainlink Labs | chainlink | Remote 为主 |
| Kraken | kraken | Remote-first |
| Ripple | ripple | — |
| Polygon | polygon | Remote |
| Circle | circle | — |
| Gemini | gemini | — |
| BitGo | bitgo | — |
| Consensys | consensys | Remote-first，MetaMask 母公司 |
| Ledger | ledger-3 | 法国，hybrid |
| Blockstream | blockstream | Remote |

### Greenhouse 系

```
GET https://boards-api.greenhouse.io/v1/boards/{slug}/jobs
```

| 公司 | slug | 备注 |
|---|---|---|
| Coinbase | coinbase | 美国，部分 remote |
| Anthropic | anthropic | 非 crypto 但 AI 顶流 |
| OpenAI | openai | 同上 |
| Stripe | stripe | fintech，AI 岗多 |
| Chainalysis | chainalysis | — |

### Ashby 系

```
GET https://api.ashbyhq.com/posting-api/job-board/{org}
```

| 公司 | slug | 备注 |
|---|---|---|
| Bybit | — | 待确认 |
| LangChain | langchain | 你 D1 目标 |
| Mem0 | — | — |
| Replicate | replicate | — |

### 自建页面（单独适配）

国内大厂作为**兜底**（海外 remote 没票时才考虑）：

| 公司 | 接入 | 优先级 |
|---|---|---|
| 字节跳动 | jobs.bytedance.com 搜索 API | P1 |
| 阿里 | talent.alibaba.com | P2 |
| 腾讯 | join.qq.com | P2 |
| Moonshot / DeepSeek / 智谱 / MiniMax | 官网 HTML | P2 |

---

## L2 - 聚合站（P0，发现新公司的关键）

这层的核心价值是**找种子清单外的 remote crypto / AI 岗**。

| 站点 | 特点 | 接入 | 优先级 |
|---|---|---|---|
| [web3.career](https://web3.career/) | Remote crypto 最全 | RSS `/feed` + HTML | P0 |
| [cryptojobslist.com](https://cryptojobslist.com/) | Remote crypto 补充 | RSS | P0 |
| [remote3.co](https://remote3.co/) | Web3 remote 专站 | HTML | P1 |
| [ai-jobs.net](https://ai-jobs.net/) | AI remote | 半公开 JSON | P1 |
| [wellfound.com](https://wellfound.com/) (AngelList) | startup | 搜索页 HTML | P1 |
| [YC Work at a Startup](https://www.workatastartup.com/) | YC 系 | 公开 company 页 | P2 |
| HN "Who is hiring?" | 每月一条高密度帖 | Algolia HN API | P1 |

### HN "Who is hiring?" 的特殊价值

AI Infra / Remote crypto 密度极高。脚本：
1. 每月 1 日抓最新 thread
2. 拿到所有 comment
3. 按 `REMOTE | Title | Company | URL` 结构化提取
4. 当作一个 source 输入

---

## L3 - 综合招聘站（P2，合规敏感）

**默认只抓公开搜索页，不登录。**

| 站点 | 风险 | 策略 |
|---|---|---|
| LinkedIn | 高 - ToS 禁止爬 | 不爬，走 Job Alert 邮件转发到 Gmail + IMAP 拉取 |
| BOSS 直聘 | 中 | 不做，海外 remote 不在这里 |

LinkedIn 迂回方案：
- LinkedIn 里配 3 个 Job Alert（remote AI Agent / remote crypto AI / AI Infra remote）
- 发到 `you@example.com`
- 本工具从 Gmail IMAP 拉 `from:jobalerts-noreply@linkedin.com` 的邮件当 passive source

---

## L4 - 被动订阅（P2，低延迟补充）

| 类型 | 来源 | 接入 |
|---|---|---|
| Telegram 群 | Crypto AI 招聘群 | Telegram Bot 监听 |
| Discord | crypto 项目方内推频道 | Discord Bot webhook |
| X 关键 KOL | 招 AI Eng 的 founder | Nitter RSS / X API |
| Gmail IMAP | LinkedIn Job Alert / 猎头群发 | IMAP |

---

## 合规边界

**红线**：
1. ❌ 不模拟登录、不用 cookie 绕过鉴权
2. ❌ 不做大规模并发（单站 1-2 req/s）
3. ❌ 不伪装 User-Agent：`job-radar/0.1 (+github.com/<me>/job-radar; personal use)`
4. ❌ 不爬 robots.txt 明确 disallow 的路径
5. ❌ 不转售 / 不公开推送给他人
6. ❌ 不爬有反爬声明的站点（LinkedIn 除外，走邮件迂回）

**绿线**：
- 所有 Lever / Greenhouse / Ashby / Workday JSON（公司主动公开）
- RSS / Atom feed
- Algolia HN API（HN 官方推荐）
- 公司自建的开放搜索 endpoint

---

## 抓取策略

- 单源 1-2 req/s，带 jitter
- 指纹去重：`sha256(company + title + normalized_location)`，3 天窗口
- 增量：每个 source 记录 `last_seen_at`，只抓新增
- 失败隔离：单源连续 3 次失败 → 告警 + 跳过
- 原文保存：`data/raw/<source>/<job_id>.json`，方便回放和改 adapter
