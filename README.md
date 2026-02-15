# MaiBot 与 Telegram 的 Adapter

运行方式：独立 MaiBot 运行。

## 如果遇到bug，或者有想添加的新功能请积极反馈

## 快速开始

推荐使用uv

1. 安装依赖（使用 uv）

```bash
# 推荐使用 uv 同步并创建虚拟环境
uv sync
# 如未安装 uv，请参考官方指引安装（或临时：pip install uv）
```

2. 生成并填写配置

```bash
python MaiBot-Telegram-Adapter\main.py  # 首次运行会生成 config.toml 并退出（Windows 示例）
# 或
python MaiBot-Telegram-Adapter/main.py    # Linux/macOS 示例
```

编辑 `config.toml`：

- `telegram_bot.token`：Telegram Bot Token（向 @BotFather 申请）
- `telegram_bot.allowed_updates`：默认只接收新消息 `["message"]`；如需接收编辑消息等，可按需加入 `"edited_message"` 等类型
- `maibot_server.host/port`：MaiBot Core WebSocket 服务（如 `ws://host:port/ws`）
- `chat`：黑白名单策略
- 代理（国内服务器需要配置）：
  - `telegram_bot.proxy_enabled = true`
  - `telegram_bot.proxy_url = "socks5://127.0.0.1:1080"` 或 `http://127.0.0.1:7890`
  - `telegram_bot.proxy_from_env = true` 可从环境变量 `HTTP_PROXY/HTTPS_PROXY/NO_PROXY` 读取

3. 运行（使用 uv）

```bash
uv run python main.py
```

## 设计目标

- 解耦、模块化：发送（MaiBot→TG）与接收（TG→MaiBot）分离
- 可扩展：按 Seg 类型扩展收发能力（text/image/voice/...）
- 对齐 `maim_message` 标准：统一的 MessageBase/Seg 适配
- 配置驱动：与 Napcat 适配器一致的模板化配置升级流程

## 目录结构

```
MaiBot-Telegram-Adapter/
  ├─ main.py                # 入口，启动 Telegram 轮询与 MaiBot 路由
  ├─ requirements.txt
  ├─ pyproject.toml
  ├─ template/template_config.toml
  └─ src/
      ├─ logger.py
      ├─ utils.py
      ├─ telegram_client.py
      ├─ mmc_com_layer.py
      ├─ config/
      │   ├─ config.py
      │   ├─ config_base.py
      │   └─ official_configs.py
      ├─ recv_handler/
      │   ├─ message_handler.py
      │   └─ message_sending.py
      └─ send_handler/
          ├─ main_send_handler.py
          └─ tg_sending.py
```

## 支持特性（初版）

- 入站（TG→MaiBot）：文本、图片（自动下载并转 base64）
- 出站（MaiBot→TG）：文本、图片（base64/URL）
- 黑白名单：与 0.7.0+ 规范一致（适配器侧校验）
 - 日志：可配置级别（TRACE/DEBUG/INFO/WARNING/ERROR/CRITICAL），支持独立 maim_message 级别；可选文件输出（轮转/保留/JSON）

### 日志配置说明（片段）

```
[debug]
level = "INFO"                       # 适配器日志级别：TRACE/DEBUG/INFO/WARNING/ERROR/CRITICAL
maim_message_level = "INFO"          # maim_message 子系统日志级别
to_file = false                       # 是否写入文件
file_path = "logs/telegram-adapter.log"
rotation = "10 MB"                   # 轮转大小或时间：如 "10 MB"、"1 day"
retention = "7 days"                 # 保留时间或数量：如 "7 days"、"14 files"
serialize = false                    # 文件日志输出 JSON
backtrace = false                    # 异常时输出完整回溯
diagnose = false                     # 更详细的异常诊断
```

也可用环境变量覆盖：`LOG_LEVEL`、`LOG_MM_LEVEL`、`LOG_FILE`、`LOG_SERIALIZE`（"1"/"true"）。

## 接入 Telegram

创建 Telegram Bot

首先，打开 Telegram，搜索 BotFather，点击 Start，然后发送 /newbot，按照提示输入你的机器人名字和用户名。

创建成功后，BotFather 会给你一个 token，请妥善保存。

如果需要在群聊中使用，需要关闭Bot的 Privacy mode，对 BotFather 发送 /setprivacy 命令，然后选择bot， 再选择 Disable。

## 后续路线

- 语音/表情/转发支持、reply 精准映射
- 管理命令/消息回执回传（echo）
