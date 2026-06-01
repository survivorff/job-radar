# 0003 - 为什么 M1 用 Gmail SMTP

**Date**: 2026-05-09
**Status**: Accepted

## 背景

推送渠道候选：Telegram Bot / Gmail SMTP / GitHub Issue / 飞书 webhook。

M1 只上一个，选哪个？

## 决策

**Gmail SMTP**，目标地址 `you@example.com`。

## 理由

1. **配置最简单**：一个 App Password + 4 个环境变量，10 分钟跑通
2. **零部署依赖**：不用 Bot、不用域名、不用 webhook
3. **用户主张 "哪个简单用哪个"**
4. **Gmail 自带看板**：搜索、归档、过滤器天然存在，不用再造
5. **JD 邮件适合阅读**：HTML 里能放 markdown 渲染 + 多链接，比 TG 消息体验好
6. **日报 + 实时** 两种场景都支持：≥90 单发一封、75-89 并到日报

## 对比其他

| 渠道 | 配置成本 | 阅读体验 | 反馈交互 | 适合 M1 |
|---|---|---|---|---|
| Gmail SMTP | 低 | 高 | 低（链接） | ✅ |
| Telegram Bot | 中 | 中 | 高（按钮） | ❌ 留 M3 |
| GitHub Issue | 低 | 中 | 中（reaction） | ❌ 留 M2 |
| 飞书 webhook | 中 | 中 | 低 | ❌ 不需要 |

Telegram 的按钮反馈更爽但 M1 的重点是"**先能收到 JD**"，不是"反馈闭环"。反馈是 M3 的事。

## 风险

- **Gmail 每日 500 封上限**：本项目日均 < 30 封，完全不担心
- **App Password 泄漏**：.env 放 gitignore + 用专门 App Password（随时可撤销）
- **邮件可能进垃圾邮件**：前 3 天手动把邮件标"非垃圾邮件"+ 添加到联系人

## 相关

- [03-channels.md](../03-channels.md)
