# job-radar

> 别再被招聘网站的噪音淹没。让 LLM 读你的简历，从 15+ 个数据源给每个职位打分，
> 把最匹配的岗位连同「为什么匹配」的中英双语理由一起发到你邮箱。

[English](README.md) | 中文

**job-radar** 是一个你自己运行的个人求职发现引擎。它抓取公开招聘源（官方 ATS API +
远程招聘站），按你的画像过滤，用真正读过你简历的 LLM 给每个职位打分，再把干净的日报推给你。

它既是独立 CLI，也是一个 [Claude / openclaw Skill](#作为-agent-skill-使用)，
让 AI agent 能替你操作。

```
采集（15+ 源） → 硬过滤 → LLM 打分（结合你的简历） → 去重 → 邮件日报
```

---

## 为什么要做这个

- **LinkedIn / 招聘站的提醒**是关键词匹配，读不懂你的简历，所以全是噪音。
- **job-radar** 把每条 JD + 你的简历一起发给 LLM，问它：*「这个真的合适吗？为什么？」*
- 你得到的是一份排好序、去过重、中英双语的日报，只留值得你花时间的岗位。

## 功能

- **开箱即用 15+ 数据源**：
  - 官方 ATS API：Lever、Greenhouse、Ashby、Workable（预置 80+ 公司）
  - 远程招聘站：RemoteOK、Remotive、WeWorkRemotely、Jobicy
  - Crypto/Web3：dejob.ai、decentrajobs
  - HN "Who is hiring?"、JSON-LD 招聘页、LinkedIn（通过 Gmail API）
- **LLM 打分**：以你的简历为上下文，输出 4 维分数 + 匹配理由 + 风险点，中英双语
- **硬过滤**：关键词、职级、地点、仅远程、按公司屏蔽/加权
- **跨站去重**（同一岗位在多个城市/数据源出现，自动合并为一条）
- **预算可控**：LLM 每日花费上限，超限自动降级到免费的关键词打分
- **邮件推送**：Resend（HTTPS，云服务器也能用）或 SMTP
- **自带 LLM**：任何 Anthropic 兼容端点（Claude、DeepSeek、各类代理）

---

## 快速开始

```bash
git clone https://github.com/survivorff/job-radar.git
cd job-radar
uv sync                                  # 安装依赖（需要 astral.sh/uv）

cp .env.example .env                     # 填入 LLM + 邮件 的 key
cp profile/example.yaml profile/me.yaml  # 描述你想要的岗位
# （可选）把简历放到 ./resume.md，启用「读简历打分」

uv run job-radar run                     # 采集 + 过滤 + 打分
uv run job-radar digest --daily --dry-run   # 本地预览日报（不发邮件）
uv run job-radar digest --daily          # 发送
```

完整步骤见 [`docs/GET-STARTED.md`](docs/GET-STARTED.md)。

---

## 配置你的画像

一切都由 `profile/me.yaml` 驱动。**track（赛道）**是一组描述你想要的岗位类型的关键词，
可以有多个。模板见 [`profile/example.yaml`](profile/example.yaml)（带注释）。

不用手改 YAML，命令行就能调：

```bash
job-radar add-keyword backend "Rust"      # 给某个 track 加关键词
job-radar exclude "Sales Manager"         # 标题含这个词的永不显示
job-radar block-company "SomeCorp"        # 屏蔽公司
job-radar boost-company "Anthropic"       # 给喜欢的公司 +15 分
job-radar disable-source remoteok         # 关掉某个数据源
job-radar show-profile                    # 打印当前配置
job-radar sources                         # 列出所有数据源 + 状态
```

---

## 命令一览

| 命令 | 作用 |
|---|---|
| `job-radar run` | 采集所有源、过滤、打分、存入 SQLite |
| `job-radar digest --daily` | 生成并发送日报（`--dry-run` 仅预览） |
| `job-radar digest --weekly` | 周报（7 天窗口） |
| `job-radar test-email` | 验证邮件通道是否正常 |
| `job-radar stats` | 近 N 天的流水线看板 |
| `job-radar label` | 交互式给匹配打标（想投/已投/边缘/拒绝/噪音） |
| `job-radar eval` | 基于你的标注算精度 / 噪音率 |
| `job-radar sources` | 列出数据源及状态 |

---

## 作为 Agent Skill 使用

job-radar 自带 `SKILL.md`，可让 [Claude Code](https://docs.anthropic.com/en/docs/agents-and-tools/skills)、
Claude Desktop 或 openclaw 替你运行（「刷新我的求职雷达」「这条为什么打高分」「别再推 QA 岗了」）。

```bash
./install.sh   # 软链到 ~/.claude/skills 和 ~/.openclaw/skills，
               # 数据放到 ~/.job-radar，并在 PATH 里装一个 job-radar 命令
```

---

## 定时运行

用 cron 定时跑（使用本地时区）：

```cron
5 * * * * /usr/local/bin/job-radar run        >> ~/.job-radar/logs/cron.log 2>&1
0 9 * * * /usr/local/bin/job-radar digest --daily >> ~/.job-radar/logs/cron.log 2>&1
```

---

## 架构

```
job_radar/
├── sources/      # 每个招聘源一个 adapter（在这里加你的）
├── pipeline/     # hard_filter → embed_recall → llm_scorer → dedupe
├── channels/     # 邮件（resend / smtp）、日报渲染
├── eval/         # 打标 + 精度统计
├── cli.py        # typer CLI
└── config.py     # .env + profile.yaml 加载
```

设计文档在 [`docs/`](docs/)。从 [`docs/00-design.md`](docs/00-design.md) 开始。

---

## 加一个数据源

新建 `job_radar/sources/<name>.py`，实现 `fetch() -> Iterable[RawJob]`，再到
`job_radar/sources/registry.py` 注册。参考 [`CONTRIBUTING.md`](CONTRIBUTING.md)
和现有的 adapter（如 `lever.py`）。欢迎提 PR 加数据源。

---

## 隐私

你的简历、画像、抓取的数据、密钥全部**留在本地**（`~/.job-radar/` 或仓库内，均已 gitignore）。
job-radar 只对外请求三类目标：招聘源、你选的 LLM 端点、你的邮件服务商。

---

## 许可证

MIT — 见 [LICENSE](LICENSE)。
