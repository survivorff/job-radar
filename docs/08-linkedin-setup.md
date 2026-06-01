# LinkedIn 接入配置（10 分钟）

> 为什么这样绕：阿里云/腾讯云封了 Gmail SMTP + IMAP 两个出站端口。
> 所以我们用 Gmail 的 **REST API（HTTPS，不封）** 替代 IMAP。
> 这个方案一次性 OAuth 授权后可无限期使用 refresh token。

---

## Step 1. LinkedIn 设 Job Alert（2 分钟）

1. 打开 https://www.linkedin.com/jobs/
2. 搜 "Senior AI Engineer"（或任何你想追踪的关键词）
3. 在搜索结果页左上角"设置工作提醒"
4. 选 **"每日"** 推送到你的 Gmail

推荐设置 3 条 Alert：
- `AI Engineer Remote`
- `Senior Web3 Backend`
- `Staff Java Engineer Crypto`

几小时后，第一封 LinkedIn Job Alert 会到达 `you@example.com`。

---

## Step 2. 创建 Google OAuth Credential（3 分钟）

1. 打开 https://console.cloud.google.com/apis/credentials
2. 顶部切到你自己的个人 Google 账号
3. 如果是第一次：点 "Create Project"，项目名 `job-radar`
4. 左侧 "Library" → 搜 "Gmail API" → **Enable**
5. 回到 "Credentials" → "+ CREATE CREDENTIALS" → **OAuth client ID**
6. 如果要求先配置 OAuth consent screen：
   - User Type: **External**
   - App name: `job-radar`
   - User support email: 你的 Gmail
   - Scopes: 先不加，后面会自动处理
   - Test users: 加上 `you@example.com`
   - Save
7. 回到 "Create OAuth client ID"
   - Application type: **Desktop app**
   - Name: `job-radar-desktop`
   - Create
8. **下载 JSON**（或复制 Client ID + Client Secret）

---

## Step 3. 本机跑一次 OAuth 授权（3 分钟）

在本地（MacBook）：

```bash
cd ~/ai/kiro/ai_learn/job-hunting
export GOOGLE_CLIENT_ID='<your-client-id>.apps.googleusercontent.com'
export GOOGLE_CLIENT_SECRET='<your-client-secret>'
uv run python scripts/gmail_auth.py
```

浏览器会弹出 Google 授权页：
- 会说 "该应用未经验证" — 正常，因为是你的个人项目，点**"高级" → "继续"**
- 选择你的 Gmail 账号
- 授予 **只读 Gmail** 权限
- 完成后浏览器显示 "Gmail auth OK"

脚本会把 refresh token 存到 `~/.job-radar/gmail_token.json`。

---

## Step 4. 传到服务器（30 秒）

```bash
# macOS
scp ~/.job-radar/gmail_token.json root@121.41.166.234:/root/.job-radar/gmail_token.json
```

验证服务器能读到：

```bash
ssh root@121.41.166.234 'ls -la ~/.job-radar/gmail_token.json'
```

---

## Step 5. 跑起来

```bash
ssh root@121.41.166.234 'job-radar run' # 或等下一个 cron 整点
```

源列表里 `gmail.linkedin` 这行的 "Fetched" 应该有数字了。

---

## 排错

**"这个应用未经验证"警告**
正常。因为是你自己项目，没 Google 审核。点"高级"继续。

**刷新 token 过期**
Google refresh token 正常情况下永久有效。除非：
- 账号改密码
- 账号开启了 2FA 后又撤销
- 6 个月没用
- 主动在 https://myaccount.google.com/permissions 撤销

任何一种情况，重跑 Step 3 即可。

**token 文件泄漏了怎么办**
去 https://myaccount.google.com/permissions 撤销 `job-radar` 授权。
重新跑 Step 3 即可。
