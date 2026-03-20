<div align="center">

![:name](https://count.getloli.com/@:MaiBot-Telegram-Adapter?name=%3AMaiBot-Telegram-Adapter&theme=miku&padding=7&offset=0&align=top&scale=1&pixelated=1&darkmode=auto)

# MaiBot-Telegram-Adapter

**MaiBot 的 Telegram 平台适配器**

将 Telegram Bot 与 [MaiBot](https://github.com/Mai-with-u/MaiBot) AI 聊天核心无缝桥接

[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python&logoColor=white)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-AGPL--v3-green.svg)](LICENSE)
[![maim_message](https://img.shields.io/badge/protocol-maim__message-orange)](https://github.com/Mai-with-u/maim_message)

</div>

---

## 简介

MaiBot-Telegram-Adapter 是 MaiBot 生态系统中的 Telegram 平台适配器，作为独立进程运行，负责在 Telegram Bot API 与 MaiBot Core 之间进行双向消息协议转换。

**工作方式：**

```
Telegram 用户 ⇄ Telegram Bot API ⇄ 本适配器 ⇄ MaiBot Core (WebSocket)
```

- **入站**（TG → MaiBot）：通过长轮询接收 Telegram 消息，解析为 `maim_message` 标准格式，经 WebSocket 转发至 MaiBot Core
- **出站**（MaiBot → TG）：接收 MaiBot Core 的响应，调用 Telegram Bot API 发送到对应的聊天

## 功能特性

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

- **黑白名单**：群组和私聊分别支持白名单/黑名单模式，支持全局封禁用户
- **代理支持**：HTTP / HTTPS / SOCKS5 代理，支持从环境变量读取
- **自定义 API 地址**：可配置 Telegram API 基础地址（适用于自建 API 代理）
- **配置版本管理**：配置文件自动升级，旧配置自动备份
- **双通道日志**：适配器日志与 `maim_message` 子系统日志独立控制级别
- **Update 去重**：防止重复处理 Telegram 消息

## 快速开始

### 前置要求

- **Python 3.10+**
- 已部署并运行的 **MaiBot Core** 实例
- Telegram Bot Token（从 [@BotFather](https://t.me/BotFather) 获取）

### 1. 克隆仓库

```bash
git clone https://github.com/exynos967/MaiBot-Telegram-Adapter.git
cd MaiBot-Telegram-Adapter
```

### 2. 安装依赖

推荐使用 [uv](https://docs.astral.sh/uv/) 进行依赖管理：

```bash
uv venv
```

```bash
uv pip install -r requirements.txt
```

### 3. 生成配置文件

```bash
uv run main.py
```

首次运行会自动生成 `config.toml` 配置文件并退出，提示你填写必要配置。

### 4. 编辑配置

编辑项目目录下的 `config.toml`，至少填写以下内容：

```toml
[telegram_bot]
token = "你的Bot Token"       # 必填

[maibot_server]
host = "localhost"             # MaiBot Core 地址
port = 8000                    # MaiBot Core 端口
```

> 详细配置说明见下方 [配置说明](#配置说明) 章节。

### 5. 启动适配器

```bash
uv run python main.py
# 或
python main.py
```

## Docker Compose 部署

仓库根目录已提供 `Dockerfile` 与 `docker-compose.yml`，默认将配置和日志分别持久化到宿主机的 `./data`、`./logs` 目录。

### 1. 首次生成配置

```bash
mkdir -p data logs
docker compose run --rm maibot-telegram-adapter
```

首次执行会在 `./data/config.toml` 生成配置模板，然后容器退出，属于正常行为。

### 2. 编辑 Docker 配置文件

编辑 `./data/config.toml`，至少填写：

```toml
[telegram_bot]
token = "你的Bot Token"

[maibot_server]
host = "你的 MaiBot Core 地址"
port = 8000
```

- 如果 **MaiBot Core 和适配器在同一个 docker compose 网络中**，`host` 请填写 MaiBot Core 的服务名
- 如果 **MaiBot Core 在宿主机或其他机器上**，`host` 请填写容器可访问的实际 IP / 域名

### 3. 启动容器

```bash
docker compose up -d
```

默认行为：

- `MAIBOT_TELEGRAM_CONFIG=/app/data/config.toml`
- `./logs` 映射到容器内 `/app/logs`
- 代理环境变量 `HTTP_PROXY` / `HTTPS_PROXY` / `ALL_PROXY` / `NO_PROXY` 会透传到容器

## 创建 Telegram Bot

1. 在 Telegram 中搜索 [@BotFather](https://t.me/BotFather)，点击 **Start**
2. 发送 `/newbot`，按提示输入机器人名称和用户名
3. 创建成功后获得 Bot Token，填入 `config.toml`

### 群聊配置

如需在群聊中使用，**必须关闭 Bot 的 Privacy Mode**：

1. 向 BotFather 发送 `/setprivacy`
2. 选择你的 Bot
3. 选择 **Disable**

> 关闭 Privacy Mode 后，Bot 才能接收群组中所有消息，而非仅 @ 消息和命令。

## 配置说明

### `[telegram_bot]` — Telegram Bot 设置

| 配置项 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `token` | string | `""` | **必填** Telegram Bot Token |
| `api_base` | string | `https://api.telegram.org` | API 基础地址（自建代理时修改） |
| `poll_timeout` | int | `20` | 长轮询超时时间（秒） |
| `allowed_updates` | list | `["message", "edited_message"]` | 监听的 Update 类型 |
| `proxy_enabled` | bool | `false` | 是否启用代理 |
| `proxy_url` | string | `""` | 代理地址 |
| `proxy_from_env` | bool | `false` | 从环境变量读取代理 |

### `[maibot_server]` — MaiBot Core 连接

| 配置项 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `host` | string | `localhost` | MaiBot Core 主机地址 |
| `port` | int | `8000` | MaiBot Core 端口 |

适配器将连接 `ws://<host>:<port>/ws`。

### `[chat]` — 消息过滤

| 配置项 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `group_list_type` | string | `whitelist` | 群组过滤模式：`whitelist` / `blacklist` |
| `group_list` | list[int] | `[]` | 群组 ID 列表 |
| `private_list_type` | string | `whitelist` | 私聊过滤模式：`whitelist` / `blacklist` |
| `private_list` | list[int] | `[]` | 用户 ID 列表 |
| `ban_user_id` | list[int] | `[]` | 全局封禁的用户 ID |

> **白名单模式**下，列表为空时不会响应任何消息，需要手动添加允许的群组/用户 ID。

### `[debug]` — 日志配置

| 配置项 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `level` | string | `INFO` | 适配器日志级别 |
| `maim_message_level` | string | `INFO` | maim_message 子系统日志级别 |
| `to_file` | bool | `false` | 是否输出日志文件 |
| `file_path` | string | `logs/telegram-adapter.log` | 日志文件路径 |
| `rotation` | string | `10 MB` | 日志轮转策略 |
| `retention` | string | `7 days` | 日志保留策略 |
| `serialize` | bool | `false` | 文件日志是否输出 JSON 格式 |
| `backtrace` | bool | `false` | 异常时输出完整堆栈回溯 |
| `diagnose` | bool | `false` | 输出详细诊断信息 |

**环境变量覆盖：**

| 环境变量 | 对应配置项 |
| --- | --- |
| `LOG_LEVEL` | `debug.level` |
| `LOG_MM_LEVEL` | `debug.maim_message_level` |
| `LOG_FILE` | `debug.file_path` |
| `LOG_SERIALIZE` | `debug.serialize`（`"1"` 或 `"true"` 启用） |

### 代理配置

在中国大陆服务器上运行时，需要配置代理才能访问 Telegram API：

```toml
[telegram_bot]
proxy_enabled = true
proxy_url = "socks5://127.0.0.1:1080"   # SOCKS5 代理
# proxy_url = "http://127.0.0.1:7890"   # 或 HTTP 代理
```

也可以通过环境变量方式：

```toml
[telegram_bot]
proxy_from_env = true   # 自动读取 HTTP_PROXY / HTTPS_PROXY / NO_PROXY
```

## 项目结构

```
MaiBot-Telegram-Adapter/
├── .github/workflows/docker-build.yml  # GitHub Actions 自动构建
├── Dockerfile                        # Docker 镜像构建文件
├── docker-compose.yml                # Docker Compose 部署示例
├── main.py                          # 程序入口：启动轮询与路由
├── requirements.txt                 # Python 依赖
├── pyproject.toml                   # 项目元数据与代码规范配置
├── template/
│   └── template_config.toml         # 配置文件模板
└── src/
    ├── logger.py                    # 日志系统（loguru 双通道）
    ├── utils.py                     # 工具函数（base64 编码、群聊判断等）
    ├── telegram_client.py           # Telegram Bot API 异步客户端
    ├── mmc_com_layer.py             # MaiBot 通信层（WebSocket 路由）
    ├── config/
    │   ├── config.py                # 配置加载、版本升级、自动备份
    │   ├── config_base.py           # 配置基类（dataclass 反射）
    │   └── official_configs.py      # 各配置节定义
    ├── recv_handler/
    │   ├── message_handler.py       # TG 消息解析 → maim_message 构建
    │   └── message_sending.py       # 向 MaiBot Core 发送消息
    └── send_handler/
        ├── main_send_handler.py     # MaiBot 响应分发
        └── tg_sending.py           # Telegram 各类型消息发送
```

## 架构概览

```
┌──────────────────────────────────────────────────┐
│              MaiBot-Telegram-Adapter              │
│                                                   │
│   ┌──────────────┐         ┌──────────────────┐  │
│   │ TelegramClient│        │  mmc_com_layer   │  │
│   │  (aiohttp)   │        │ (maim_message    │  │
│   │              │        │  Router/WS)      │  │
│   └──────┬───────┘         └────────┬─────────┘  │
│          │                          │             │
│   ┌──────┴───────┐         ┌────────┴─────────┐  │
│   │ recv_handler │         │  send_handler    │  │
│   │ TG → MaiBot  │         │  MaiBot → TG     │  │
│   └──────────────┘         └──────────────────┘  │
│                                                   │
└──────────────────────────────────────────────────┘
        ↕ HTTPS                      ↕ WebSocket
   Telegram API               MaiBot Core (AI)
```

## 反馈与贡献

如果遇到 Bug 或有功能建议，欢迎通过 [Issues](https://github.com/exynos967/MaiBot-Telegram-Adapter/issues) 反馈！

## 许可证

本项目基于 AGPLv3 许可证开源。
