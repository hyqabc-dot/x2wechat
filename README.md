# X to WeChat Monitor

自动监控X(Twitter)用户推文并推送到微信的工具。

## 🌟 功能特性

- 🌐 **云端运行**: 基于GitHub Actions，24小时自动运行
- 📱 **微信推送**: 通过Server酱推送到个人微信
- 🈲 **智能翻译**: 英文推文自动翻译为中文
- 🔄 **定时监控**: 每10分钟检查一次新推文
- 💰 **完全免费**: 使用GitHub免费额度

## 📦 监控的用户

当前监控以下X用户的推文：
- @poyincom
- @didengshengwu
- @0427SMtieshou
- @Svwang1
- @cnfinancewatch
- @elonmusk

## 🚀 使用方法

此工具已配置完毕，会自动：
1. 每10分钟检查一次新推文
2. 发现新推文时推送到微信
3. 提供中英文对照翻译

## 📱 推送格式示例

```
@elonmusk:
Tesla 股价 是 上涨 今天 和 公司 宣布了 新 AI技术

原文: Tesla stock price is going up today and the company announced new AI technology
https://x.com/elonmusk/status/1234567890
```

## ⚙️ 配置说明

- 推送方式: Server酱
- 运行频率: 每10分钟
- 数据源: Nitter RSS (多个镜像站点)
- 状态保存: 自动保存到仓库

## 🔍 查看运行状态

- 在GitHub Actions页面查看运行日志
- 检查state.json文件的更新时间
- 关注微信推送消息

---

*此工具由GitHub Actions驱动，完全自动化运行。*