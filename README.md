<div align="center">

![:name](https://count.getloli.com/@:MaiBot-Telegram-Adapter?name=%3AMaiBot-Telegram-Adapter&theme=miku&padding=7&offset=0&align=top&scale=1&pixelated=1&darkmode=auto)

# MaiBot-Telegram-Adapter

**MaiBot 的 Telegram 平台适配器插件**

将 Telegram Bot 与 [MaiBot](https://github.com/Mai-with-u/MaiBot) 无缝桥接

[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python&logoColor=white)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-AGPL--v3-green.svg)](LICENSE)
[![maibot-plugin-sdk](https://img.shields.io/badge/SDK-maibot--plugin--sdk-orange)](https://github.com/Mai-with-u/maibot-plugin-sdk)

</div>

### 安装

将本仓库 clone 到 MaiBot 的 `plugins/` 目录下：

```bash
cd /path/to/MaiBot/plugins
git clone https://github.com/exynos967/MaiBot-Telegram-Adapter.git
```

### 依赖

- `maibot_sdk` >= 2.0.0（由 MaiBot 主程序提供）
- `aiohttp` >= 3.9.0（MaiBot 主程序已包含）
- `aiohttp-socks` >= 0.8.4（可选，使用 SOCKS 代理时需要）

如需 SOCKS 代理支持：

```bash
pip install aiohttp-socks
```

## 配置

首次加载后会在插件目录生成 `config.toml`，编辑该文件：

```toml
[plugin]
enabled = true                # 启用插件
config_version = "0.1.0"

[telegram_bot]
token = "你的Bot Token"       # 必填，从 @BotFather 获取
api_base = "https://api.telegram.org"
poll_timeout = 20
proxy_enabled = false
proxy_url = ""                # 例如 socks5://127.0.0.1:1080 或 http://127.0.0.1:7890
proxy_from_env = false

[chat]
group_list_type = "whitelist" # whitelist / blacklist
group_list = []               # chat_id 列表
private_list_type = "whitelist"
private_list = []             # 用户 ID 列表
ban_user_id = []              # 全局屏蔽用户
```

配置也可通过 MaiBot WebUI 的插件配置页面进行热重载修改。

### MaiBot 主配置

MaiBot Core 仍会用主配置里的 bot 平台账号识别“机器人自己”。启用 Telegram 后，请在 MaiBot 主配置的 `[bot]` 中加入 Telegram Bot 的数字 ID：

```toml
[bot]
platforms = ["telegram:123456789"]
```

也可以使用 `tg:123456789`。Bot 数字 ID 会在插件启动成功后通过日志 `Telegram Bot: id=...` 输出。若缺少该配置，MaiBot 的历史消息/提示词中可能无法把 bot 自身识别为配置的昵称。

## 功能

### 消息类型支持

| 消息类型 | 入站（TG → MaiBot） | 出站（MaiBot → TG） |
| :---: | :---: | :---: |
| 文本 | ✅ | ✅ |
| 图片 | ✅ 自动下载转 base64 | ✅ base64 / URL |
| 语音 | ✅ 自动下载转 base64 | ✅ base64 |
| 贴纸 | ✅ 转 emoji 类型 | ✅ 以动图发送 |
| GIF 动图 | ✅ 转 emoji 类型 | ✅ 以动图发送 |
| 视频 | — | ✅ URL |
| 文件 | ✅ 转文本标记 | ✅ URL |
| 回复消息 | ✅ 关联消息 ID | ✅ reply_parameters |
| @Bot | ✅ 多种识别方式 | — |

### 其他特性

- **黑白名单**：群组和私聊分别支持白名单/黑名单模式
- **代理支持**：HTTP / HTTPS / SOCKS5 代理
- **自定义 API 地址**：适用于自建 Telegram API 代理
- **Topic 分流**：同群不同话题独立会话
- **@Bot 识别**：支持 mention entity、reply、文本兜底匹配
- **WebUI 热重载**：配置修改后自动重连

## 创建 Telegram Bot

1. 在 Telegram 中搜索 [@BotFather](https://t.me/BotFather)
2. 发送 `/newbot`，按提示创建
3. 获得 Bot Token，填入配置

### 群聊使用

如需在群聊中接收所有消息，必须关闭 Bot 的 Privacy Mode：

1. 向 BotFather 发送 `/setprivacy`
2. 选择你的 Bot
3. 选择 **Disable**

## 架构

```
MaiBot Host
    ↕ maibot_sdk MessageGateway (duplex)
MaiBot-Telegram-Adapter Plugin
    ↕ HTTPS (long-polling / Bot API)
Telegram
```

- 入站：长轮询 → 消息转换 → `ctx.gateway.route_message()` → Host
- 出站：Host → `@MessageGateway` handler → Telegram Bot API

## 许可证

本项目基于 AGPLv3 许可证开源。
