.PHONY: install init run digest daily weekly stats lint format test clean

install:
	uv sync

# 创建 .env 和 profile/me.yaml（从 example 复制）
init:
	@test -f .env || cp .env.example .env && echo "✅ .env created"
	@test -f profile/me.yaml || cp profile/example.yaml profile/me.yaml && echo "✅ profile/me.yaml created"

# 采集 + 过滤 + 入库（不发邮件）
run:
	uv run job-radar run

# 从库里查当日匹配 + 发日报邮件
daily:
	uv run job-radar digest --daily

weekly:
	uv run job-radar digest --weekly

# 发一封测试邮件验证 SMTP
test-email:
	uv run job-radar test-email

stats:
	uv run job-radar stats

# 一次跑完全流程
e2e: run daily

# -------- Dev --------

lint:
	uv run ruff check .

format:
	uv run ruff format .

test:
	uv run pytest

clean:
	rm -rf data/*.sqlite runs/*.json logs/*.log
