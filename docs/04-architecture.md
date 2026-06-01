# 04 - 技术架构

> 代码分层、数据模型、一次 run 的时序。

---

## 模块树

```
job_radar/
├── cli.py                  # typer 入口：run / backfill / eval / export
├── config.py               # .env + profile.yaml 加载
├── models.py               # pydantic 领域模型
├── db.py                   # SQLAlchemy 模型 + 连接池
├── sources/
│   ├── base.py             # Source protocol
│   ├── lever.py            # OKX / Binance / ... 共用
│   ├── bytedance.py
│   ├── ai_jobs_net.py
│   └── ...
├── pipeline/
│   ├── hard_filter.py
│   ├── embed_recall.py
│   ├── llm_scorer.py
│   ├── dedupe.py
│   └── calibrate.py        # 反馈调参
├── channels/
│   ├── base.py
│   ├── github_issue.py
│   ├── email.py
│   └── telegram.py
├── jobs/                   # APScheduler 定时任务
│   ├── scheduler.py
│   └── tasks.py
├── trace.py                # 运行日志 → runs/*.json（抄 showcase-a）
└── eval/
    ├── golden.py           # 金标集
    └── metrics.py
```

---

## 数据模型（SQLite 表）

### sources
| col | type | notes |
|---|---|---|
| id | pk | |
| name | str | 'okx-lever' |
| last_run_at | datetime | |
| last_success_at | datetime | |
| consecutive_failures | int | |

### jobs
| col | type | notes |
|---|---|---|
| id | pk | |
| fingerprint | str, unique | sha256(company+title+location) |
| source_id | fk | |
| company | str | |
| title | str | |
| location | str | |
| department | str | nullable |
| seniority_guess | str | |
| salary_text | str | 原始薪资字符串 |
| salary_min_cny_year | int | 归一化后 |
| salary_max_cny_year | int | |
| description | text | 完整 JD |
| apply_url | str | |
| posted_at | datetime | |
| first_seen_at | datetime | |
| last_seen_at | datetime | |
| raw | json | 原始响应 |

### matches
| col | type | notes |
|---|---|---|
| id | pk | |
| job_id | fk | |
| stage1_passed | bool | |
| stage1_reason | str | |
| matched_tracks | json | |
| stage2_cosine | float | nullable |
| stage3_overall | int | nullable |
| stage3_dims | json | nullable |
| stage3_reasons | json | |
| stage3_risks | json | |
| suggested_resume_version | str | |
| cover_letter_angle | str | |
| scored_at | datetime | |
| cost_cny | float | LLM 花费 |

### pushes
| col | type | notes |
|---|---|---|
| id | pk | |
| match_id | fk | |
| channel | str | |
| tier | str | |
| sent_at | datetime | |
| external_ref | str | 如 GH issue url / TG message_id |

### feedback
| col | type | notes |
|---|---|---|
| id | pk | |
| push_id | fk | |
| action | enum | want / reject / applied / missed |
| at | datetime | |

---

## 一次 run 时序

```
┌────────────────┐
│ scheduler tick │ (每小时)
└───────┬────────┘
        ▼
 ┌────────────────┐
 │ run_id = uuid  │
 │ start trace    │
 └───────┬────────┘
         ▼
 ┌──────────────────────────┐
 │ for each source (并行)   │
 │   new_jobs = src.list()  │
 │   upsert jobs            │
 └───────┬──────────────────┘
         ▼
 ┌─────────────────────┐
 │ stage1: hard_filter │
 │ update matches      │
 └───────┬─────────────┘
         ▼
 ┌─────────────────────┐
 │ stage2: embed_recall│
 └───────┬─────────────┘
         ▼
 ┌─────────────────────┐
 │ stage3: llm_scorer  │
 │ (budget guard)      │
 └───────┬─────────────┘
         ▼
 ┌─────────────────────┐
 │ tier + dedupe       │
 │ enqueue to channels │
 └───────┬─────────────┘
         ▼
 ┌─────────────────────┐
 │ channels.send()     │
 │ record pushes       │
 └───────┬─────────────┘
         ▼
 ┌─────────────────────┐
 │ end trace           │
 │ write runs/*.json   │
 └─────────────────────┘
```

每步 try/except 独立。异常写 trace 但不中断下游（除非 stage 全挂）。

---

## 定时调度

```python
# jobs/scheduler.py (简化示意)
scheduler.add_job(run_pipeline, "cron", minute=5)           # 每小时 5 分采集+评分
scheduler.add_job(send_daily_digest, "cron", hour=9)        # 每日 09:00 日报
scheduler.add_job(send_weekly_digest, "cron", day_of_week="sun", hour=21)
scheduler.add_job(reconcile_feedback, "cron", hour=3)       # 每日 03:00 拉 GH reactions
scheduler.add_job(calibrate, "cron", day_of_week="sun", hour=4)  # 每周调参
scheduler.add_job(backup_db, "cron", day_of_week="sun", hour=2)
```

---

## 配置分层

```
os.env → .env → profile/me.yaml → runtime overrides
```

`config.py` 用 `pydantic-settings` 统一加载。运行时覆盖走 CLI flag。

---

## Trace 设计

复用 showcase-a 的思路：每次 run 输出一个 JSON 到 `runs/YYYY-MM-DDTHH-MM-SS_<uuid>.json`：

```json
{
  "run_id": "uuid",
  "started_at": "...",
  "ended_at": "...",
  "sources": [
    {"name": "okx-lever", "fetched": 23, "new": 3, "errors": []}
  ],
  "stages": {
    "hard_filter": {"in": 47, "out": 12},
    "embed_recall": {"in": 12, "out": 6},
    "llm_scorer": {"in": 6, "out": 6, "cost_cny": 0.014}
  },
  "pushes": [
    {"channel": "github_issue", "job_id": "...", "tier": "high"}
  ]
}
```

出问题时直接看最近 run 的 json，不用翻日志。

---

## 测试策略

- 单测：`sources/*` mock HTTP、`pipeline/*` 用小样本
- 集成测：`tests/integration/test_e2e.py` 用固定样本跑完整 pipeline，不调 LLM（mock scorer）
- Eval：`make eval` 跑金标集，输出 P/R/F1 + 每 stage 贡献

