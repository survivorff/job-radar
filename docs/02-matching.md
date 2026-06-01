# 02 - 匹配算法

> 怎么判断这条 JD 适合我。三段流水线，从便宜到贵。海外 remote crypto 权重高。

---

## 总原则

```
采集 1000 条  →  Stage 1 (硬规则) 200 条  →  Stage 2 (向量) 50 条  →  Stage 3 (LLM) 20 条  →  推送 5 条
         免费            免费                    近免费                 ~¥0.002/条
```

规则：**越便宜的过滤越先跑**。LLM 成本是全链路瓶颈。

---

## Stage 1 - 硬规则过滤

配置在 `profile/me.yaml`，零 LLM 成本，<10ms/条。

只做 4 件事：
1. `exclude_keywords` 一票否决（算法研究员 / AI 运营 / 实习 等）
2. `seniority_blocklist` 过滤（Junior / Intern）
3. `include_keywords + required_any` 必须命中至少一条 track
4. `location_allowlist` 必须命中（allowlist 覆盖海外 remote + 亚太枢纽 + 国内一线）

**已移除**：薪资硬门槛（你的要求，让 LLM 综合判断）

```python
def hard_filter(job: RawJob, profile: Profile) -> FilterResult:
    # 1. exclude 一票否决
    if any(kw in job.text for kw in profile.exclude_keywords):
        return FilterResult(passed=False, reason="excluded keyword")
    # 2. 职级黑名单
    if any(kw in job.title for kw in profile.seniority_blocklist):
        return FilterResult(passed=False, reason="seniority blocked")
    # 3. 匹配 track（至少一条）
    matched = []
    for track in profile.tracks:
        hits = sum(1 for kw in track.include_keywords if kw.lower() in job.text.lower())
        if hits >= 2 and any(kw in job.text for kw in track.required_any):
            matched.append(track.id)
    if not matched:
        return FilterResult(passed=False, reason="no track matched")
    # 4. 地点
    if job.location and not any(loc.lower() in job.location.lower() for loc in profile.location_allowlist):
        return FilterResult(passed=False, reason=f"location {job.location} not allowed")
    return FilterResult(passed=True, matched_tracks=matched)
```

### Remote 识别

location 字段在不同平台写法多：`Remote` / `Worldwide` / `Global` / `Anywhere` / `Remote - APAC` / `Remote (US/EU)` 等。

在 `hard_filter.py` 里统一归一化：

```python
REMOTE_MARKERS = {"remote", "worldwide", "global", "anywhere", "distributed"}
def is_remote(loc: str) -> bool:
    return any(m in loc.lower() for m in REMOTE_MARKERS)
```

`is_remote` 的结果作为 `job.is_remote: bool` 字段存入 db，供 Stage 3 加权用。

---

## Stage 2 - 向量召回

**目的**：扔掉"关键词命中但语义不匹配"的（比如硬规则放过的"RAG 客服运营岗"）。

- **Embedding**：`BAAI/bge-m3` via `fastembed`（本地跑，免费）
- **Profile vector**：resume + 每条 track 的 `ideal_jd` 拼起来，做一次 embedding 存盘
- **Job vector**：JD title + description，做 embedding
- **相似度**：cosine
- **阈值**：初始 0.35，跑 2 周后按反馈校准

```python
def embed_recall(job: Job, profile_vec: np.ndarray, threshold: float = 0.35) -> float:
    job_vec = embed(job.text)
    return cosine(job_vec, profile_vec)
```

---

## Stage 3 - LLM 精评

**输入**：resume + JD + matched_tracks + `is_remote` + `track.prefer_remote_overseas`
**输出**：结构化 JSON（pydantic 强约束）
**模型**：DeepSeek-Chat（~¥0.002/条）

### Prompt 结构

```
System:
你是 Frank 的个人求职顾问。基于简历和 JD，输出 JSON 评分。
评分维度：
- tech_stack：技术栈命中度 (0-100)
- scenario：业务场景契合度 (0-100)
- seniority：职级 / 经验匹配 (0-100)
- company_fit：公司 / 赛道吸引力 (0-100)

计算 overall：
  base = 0.3*tech_stack + 0.3*scenario + 0.2*seniority + 0.2*company_fit
  如果 track 包含 crypto_ai 且岗位 is_remote=true：overall = base + 8（上限 100）
  如果 track 包含 crypto_ai 且岗位在"Asia/海外"但不 remote：overall = base + 4
  其他情况：overall = base

只输出 JSON，不要解释。

User:
<resume>{{resume_text}}</resume>
<job>
Company: {{company}}
Title: {{title}}
Location: {{location}} (is_remote={{is_remote}})
Description: {{description}}
</job>
<matched_tracks>{{tracks}}</matched_tracks>

{{few_shot_examples}}
```

### 输出 Schema

```python
class Score(BaseModel):
    overall: int = Field(ge=0, le=100)
    dims: dict[str, int]
    reasons: list[str] = Field(max_items=3)
    risks: list[str] = Field(max_items=3)
    suggested_resume_version: Literal["V1", "V2", "V3"]
    cover_letter_angle: str | None = None
```

### 成本熔断

```python
if daily_llm_spend >= profile.budget.daily_llm_cny:
    logger.warning("daily budget hit, fallback to stage 2 only")
    return Score(overall=int(stage2_cosine * 100), ...)  # 降级
```

---

## 反馈闭环（M3 起启用）

每次邮件带 3 个反馈链接：👍 want / 👎 reject / ⏸️ applied。点击 → 轻量 FastAPI / Vercel function → 写 SQLite `feedback` 表。

每周日 03:00 跑 `pipeline/calibrate.py`：

1. 统计 Stage 1-3 各阶段 P/R
2. Stage 1 precision > 0.95 但 recall < 0.5 → 放松硬规则
3. Stage 3 overall ≥ 80 但 👎 比例 > 30% → 提高阈值
4. 👍 样本加入 LLM few-shot（最多保留最新 10 条）

**第一个月只收数据不调参**，避免小样本瞎调。

---

## 金标数据集（Eval）

抓到第一周人工标 30 条作为金标：

- 10 条"我一定想投"（大概率是 OKX Senior AI Agent + LangChain + Chainlink 类）
- 10 条"边缘，看心情"
- 10 条"明确不感兴趣"（算法研究 / 纯前端 / 初级）

每次改 prompt / 阈值都跑一遍金标，P/R/F1 不退步才上线。直接复用 `showcase-a` 的 Eval Harness 设计。
