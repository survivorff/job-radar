# 远程 Crypto / Web3 / AI 招聘网站汇总

> 持续更新。标 ✅ 的已接入 job-radar，标 🟡 的有 API 但还没写 adapter，标 ❌ 的需要 playwright 或登录。

---

## 已接入 ✅

| 站点 | 类型 | 接入方式 | 特点 |
|---|---|---|---|
| **dejob.ai** | Crypto 远程 | JSON API (`/api/worker/topics`) | 中文为主，Web3 远程岗密度极高，你之前几份工作来源 |
| **decentrajobs.com** | Crypto 远程 | JSON API (`/api/jobs`) | 英文，curated，Binance/Coinbase 等大厂 |
| **remoteok.com** | 通用远程 | JSON API (`/api`) | 大量 remote 岗，tag 过滤 crypto/ai/backend |
| **remotive.com** | 通用远程 | JSON API (`/api/remote-jobs`) | 分类清晰，software-dev / devops / data |
| **jobicy.com** | 通用远程 | RSS feed | 按 category 过滤，支持 part-time/contract |
| **weworkremotely.com** | 通用远程 | RSS feed | 编程 + DevOps 分类（阿里云被 CF 拦） |
| **HN "Who is hiring?"** | 月度帖 | Algolia HN API | AI/Crypto remote 密度极高 |
| **Lever / Greenhouse / Ashby** | 公司官方 ATS | 公开 JSON API | 88 家公司已接入 |

## 待接入 🟡（有 API 或 RSS，可写 adapter）

| 站点 | URL | 接入方式 | 备注 |
|---|---|---|---|
| **crypto.jobs** | crypto.jobs | 需要嗅探 API（页面是 SPA） | 4000+ crypto 岗，remote 占 87% |
| **remote3.co** | remote3.co | 308 redirect → 可能改域名了 | Web3 remote 专站 |
| **cryptocurrencyjobs.co** | cryptocurrencyjobs.co | SPA，需 playwright 或 API 嗅探 | 老牌 crypto 招聘站 |
| **web3career.xyz** | web3career.xyz | 301 → 可能合并到 web3.career | 新站 |
| **builtin.com** | builtin.com/remote | HTML 解析 | 美国 remote 岗多 |
| **angel.co / wellfound** | wellfound.com | SPA（需登录看详情） | YC/startup 系 |
| **arc.dev** | arc.dev | SPA（无公开 API） | 远程开发者平台 |
| **himalayas.app** | himalayas.app | RSS 404 了 | 远程岗聚合 |
| **nodesk.co** | nodesk.co | HTML | 远程岗 |
| **flexjobs.com** | flexjobs.com | 付费站（需账号） | 远程 + 兼职 |
| **toptal.com** | toptal.com | 需登录 | 高端远程 freelance |
| **gun.io** | gun.io | 需登录 | 远程 freelance |
| **turing.com** | turing.com | 需登录 | 远程全职 |
| **lemon.io** | lemon.io | 需登录 | 远程 contract |
| **andela.com** | andela.com | 需登录 | 远程全职 |

## Cloudflare 拦截 ❌（需 playwright）

| 站点 | URL | 备注 |
|---|---|---|
| **web3.career** | web3.career | 74000+ 岗，最大的 crypto 招聘站 |
| **cryptojobslist.com** | cryptojobslist.com | RSS 被 CF 拦 |
| **weworkremotely.com** | weworkremotely.com | 阿里云 IP 被拦（本地 OK） |

## 国内平台

| 站点 | URL | 接入方式 | 备注 |
|---|---|---|---|
| **BOSS 直聘** | zhipin.com | 需登录 | 国内最大，但远程岗少 |
| **拉勾** | lagou.com | 需登录 | 互联网岗 |
| **猎聘** | liepin.com | 需登录 | 中高端 |
| **V2EX 酷工作** | v2ex.com/go/jobs | HTML | 远程 + 兼职帖 |
| **电鸭** | eleduck.com | HTML | 远程工作社区 |
| **程序员客栈** | proginn.com | 需登录 | 远程兼职 |

## LinkedIn（迂回方案）

不直接爬。通过 **Gmail REST API** 读取 LinkedIn Job Alert 邮件：
1. 在 LinkedIn 设 3 个 Job Alert（每日推送到 Gmail）
2. 本机跑一次 OAuth 授权（`scripts/gmail_auth.py`）
3. 服务器通过 HTTPS 读 Gmail → 解析 LinkedIn 邮件里的 JD 链接

详见 `docs/08-linkedin-setup.md`。

---

## 下一步扩展优先级

1. **crypto.jobs** — 嗅探 SPA 的 API（大概率有 `/api/jobs` 或 GraphQL）
2. **V2EX 酷工作** — HTML 解析，远程兼职帖多
3. **电鸭 eleduck.com** — 中文远程社区
4. **playwright 打开 web3.career** — 最大的 crypto 招聘站
5. **LinkedIn Gmail 接入** — 等你配 OAuth
