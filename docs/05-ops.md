# 05 - 运维 / 成本 / 合规

> 怎么把它稳定跑起来，花多少钱，出问题怎么办。

---

## 部署阶段

### M1-M4：本地跑

```bash
# crontab -e (macOS / Linux; cron uses the local timezone)
5 * * * * cd ~/code/job-radar && /usr/local/bin/uv run job-radar run >> logs/radar.log 2>&1
# daily digest at 09:00 local time
0 9 * * * cd ~/code/job-radar && /usr/local/bin/uv run job-radar digest --daily
# weekly digest Sunday 21:00 local time
0 21 * * 0 cd ~/code/job-radar && /usr/local/bin/uv run job-radar digest --weekly
```

**弱点**：电脑关机不跑。海外 remote crypto 岗延迟敏感 → M5 迁 GitHub Actions。

### M5：GitHub Actions 托管

```yaml
# .github/workflows/radar.yml
name: radar
on:
  schedule:
    - cron: '5 * * * *'   # UTC，每小时
    - cron: '0 1 * * *'   # UTC 01:00 = 北京 09:00，发日报
  workflow_dispatch:

jobs:
  run:
    runs-on: ubuntu-latest
    concurrency: radar-singleton
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
      - run: uv sync
      - run: uv run job-radar run
        env:
          DEEPSEEK_API_KEY: ${{ secrets.DEEPSEEK_API_KEY }}
          SMTP_HOST: smtp.gmail.com
          SMTP_PORT: 587
          SMTP_USER: ${{ secrets.SMTP_USER }}
          SMTP_PASS: ${{ secrets.SMTP_PASS }}
          SMTP_FROM: ${{ secrets.SMTP_USER }}
          SMTP_TO: ${{ secrets.SMTP_USER }}
      - name: commit state
        run: |
          git add data/radar.sqlite runs/
          git -c user.email=bot@local -c user.name=radar-bot commit -m "chore: radar run ${{ github.run_id }}" || exit 0
          git push
```

**数据持久化**：SQLite 文件随每次 run commit 回仓库 `data/` 目录。私仓，不担心暴露。

**成本**：GitHub Actions 对私仓有限额（免费账户 2000 min/月），一次 run < 2 min → 24 次/天 = 48 min/天 = 1440 min/月，**在额度内**。

---

## 成本预算

| 项 | 月度 | 备注 |
|---|---|---|
| LLM 精评（DeepSeek） | ≤ ¥30 | 硬上限 ¥5/天 |
| Embedding | ¥0 | 本地 fastembed |
| Telegram | ¥0 | Bot API 免费 |
| Email (Resend) | ¥0 | 100 封/日免费 |
| GitHub Actions | ¥0 | 免费额度内 |
| 域名 / VPS | ¥0 | 不需要 |
| **总计** | **< ¥50/月** | |

硬熔断：当日 LLM 花费 ≥ `JOB_RADAR_DAILY_LLM_BUDGET`（默认 5），跳过 Stage 3，降级用 Stage 2 cosine × 100 当 overall。

---

## 监控

### 自己监控自己

- 连续 3 次 run 失败 → 发 TG 告警给自己
- 某个 source 连续 3 次失败 → 标记 `disabled`，告警
- LLM 花费日增速异常（比昨天高 3x）→ 告警
- 24 小时无新 JD 入库 → 告警（大概率所有 source 都挂了）

### 简易 dashboard

`job-radar stats` 输出：
```
Last 7 days:
  Crawled: 342
  Passed hard filter: 89
  Scored by LLM: 23
  Pushed: 17
    high (≥90): 3
    med (75-89): 11
    low (60-74): 3
  User feedback: 5 want / 2 applied / 1 reject / 9 no action
  LLM cost: ¥1.47
```

---

## 合规

### 抓取行为自律

- User-Agent: `job-radar/0.1 (+github.com/<me>/job-radar; personal use; contact: <email>)`
- 所有请求带 10s 超时
- 单站 QPS ≤ 2
- 遵守 robots.txt
- 不爬需要登录的页面

### 数据使用

- JD 内容只用于本人求职匹配，不转售、不二次分发
- 仓库公开时，`data/` 目录内容脱敏（去掉原始 description，只留 title/company/url/score 等元数据）
- 反馈数据（feedback）永不公开

### 开源脱敏（M6）

开源前用 `git filter-repo` 清掉：
- profile/me.yaml 历史版本
- data/ 的所有 commit
- .env 相关历史

---

## 失败恢复

### 场景 1：某个 source 的站点改版

- 单测挂 → CI 红 → 修 adapter
- 抓取层把失败的单条原始响应存 `data/raw_failed/`，方便重放

### 场景 2：LLM 服务全挂

- 自动切备用 provider（LiteLLM fallback）
- 都挂就降级到 Stage 2-only 档位

### 场景 3：SQLite 损坏

- 每周日 02:00 备份 `data/radar.sqlite` → `data/backups/radar-YYYYMMDD.sqlite`
- 保留 4 周
- 损坏时从最新备份恢复，重放最近 7 天 raw

### 场景 4：GitHub 限流

- GH API 有限流（5000 req/hour）。issue 创建批量化，错峰发送。

---

## 发布节奏

- 一期本地跑，不对外
- 二期 GitHub Actions 托管，仍不对外
- 三期（M6）脱敏开源到 `github.com/<me>/job-radar`

**关键**：开源版本只是"工具 + 默认画像模板"，我自己的 profile/me.yaml 永远不发。
