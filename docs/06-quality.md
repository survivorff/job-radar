# 06 - Quality / Satisfaction Criteria

> 用可度量的指标定义"满意"，避免"感觉不好"这种不可复现的评价。

---

## 1. 指标

### 1.1 精度 (Precision)

每次日报里每条 JD 打一个标签：

| 标签 | 含义 |
|---|---|
| 👍 `want` | 想投 / 值得深读 |
| ⏸️ `applied` | 已投 / 已投同岗 |
| 🤔 `maybe` | 边缘，不拒绝 |
| 👎 `reject` | 不想投 / 方向不对 |
| ⚠️ `noise` | 根本不该过滤 — 明显的误杀（e.g. UX Researcher） |

精度公式：
```
P@high = (want + applied) / |high|
P@med  = (want + applied + maybe) / |med|
```

### 1.2 目标

| 指标 | 目标 | 意义 |
|---|---|---|
| P@high | ≥ 80% | 高分档里至少 8/10 是真命中 |
| P@med | ≥ 60% | 中档至少一半可看 |
| noise 比例 (all tiers) | ≤ 10% | 控制"明显杀错"的下限 |
| 高+中总数 | 5 ≤ n ≤ 25 | 太多是噪声，太少是漏网 |
| Dedup rate | ≤ 5% | 同岗位多地/多源去重 |
| target list recall (weekly) | ≥ 90% | A 类公司的新岗没漏 |

### 1.3 满意定义

**连续 3 个工作日 P@high ≥ 80% 且 P@med ≥ 60% 且 noise ≤ 10%**。

之前：先优化到人工抽查 1 次达标即可部署。

---

## 2. 怎么评估

### 2.1 命令

```bash
# 交互式打标（上下键选，回车确认；支持 skip）
job-radar label --kind daily

# 查看精度报告
job-radar eval

# 导出金标集（用于跨迭代对比）
job-radar eval --export data/golden.json
```

### 2.2 黄金集 (golden set)

- 每次重大改动前：导出当前 labels → `data/golden-YYYYMMDD.json`
- 改动后：重算打分 → 跟 golden 对比 P@high / P@med 是否退步
- 退步不部署

### 2.3 Noise 来源的典型例子

从 2026-05-09 的第一批日报里抽出来的"应该过滤掉"但漏掉的：

- **UX / Graphic / Marketing / Partnership** → 已加 exclude_keywords
- **QA / Investigation / Compliance** → 已加
- **Product Manager / Product Operations** → 已加
- **General Manager / Listing Manager** → 已加
- **Data Scientist (LLM) but really 算法岗** → 还没处理，M3 LLM 打分应该能识别
- **同公司同岗位多城市重复** (LangChain Solutions Architect × 6 城) → 需要 title-prefix dedup
- **Big Data/Search/Electron PM 虽是 Senior 但不是我赛道** → 取决于 track 匹配，但 scenario 分不够低；M3 LLM 改善

---

## 3. 迭代改动轨道

每次迭代按顺序：

1. 改代码
2. 本地跑 `job-radar run` 重新打分
3. `job-radar eval` 看新指标 vs golden
4. 退步就回滚 / 前进就 commit
5. 达标才 rsync 到服务器

---

## 4. 当前基线 (2026-05-09)

| 指标 | 基线 |
|---|---|
| 源数 | 7 active |
| 总入库 | 3048 |
| 过滤通过 | 266 |
| Tier 分布 | high 9 / med 152 / low 105 |
| P@high | 未人工标 (待 label 一次) |
| Dedup rate | ~30% (LangChain 6 城 / OKX 同岗多地) |

下一个改动目标：把 dedup rate 降到 ≤ 5%。
