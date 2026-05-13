"""Telegram Bot API 适配器插件。

承担完整的 Telegram 消息网关职责：
1. 通过长轮询接收 Telegram 消息并转换为 Host 侧结构。
2. 将 Host 出站消息转换为 Telegram API 调用并发送。
3. 通过 MessageGateway 装饰器注册为双工消息网关。
"""

from __future__ import annotations

from typing import Any, ClassVar, Dict, Optional, cast

import asyncio
import contextlib

from maibot_sdk import MaiBotPlugin, MessageGateway, PluginConfigBase

from .codecs import TelegramInboundCodec
from .codecs.outbound import TelegramOutboundCodec
from .config import TelegramPluginSettings
from .constants import PLATFORM_NAME, TELEGRAM_GATEWAY_NAME
from .filters import TelegramChatFilter
from .telegram_client import TelegramClient
from .utils import is_group_chat


class TelegramAdapterPlugin(MaiBotPlugin):
    """Telegram 消息网关插件。"""

    config_model: ClassVar[type[PluginConfigBase] | None] = TelegramPluginSettings

    def __init__(self) -> None:
        super().__init__()
        self._tg_client: Optional[TelegramClient] = None
        self._inbound_codec: Optional[TelegramInboundCodec] = None
        self._outbound_codec: Optional[TelegramOutboundCodec] = None
        self._chat_filter: Optional[TelegramChatFilter] = None
        self._poll_task: Optional[asyncio.Task[None]] = None
        self._stop_requested: bool = False

    async def on_load(self) -> None:
        """插件加载时根据配置决定是否启动轮询。"""
        await self._restart_if_needed()

    async def on_unload(self) -> None:
        """插件卸载时停止轮询并关闭客户端。"""
        await self._stop_polling()

    async def on_config_update(self, scope: str, config_data: Dict[str, Any], version: str) -> None:
        """配置更新后重载连接状态。"""
        if scope != "self":
            return
        self.set_plugin_config(config_data)
        await self._restart_if_needed()

    @MessageGateway(
        name=TELEGRAM_GATEWAY_NAME,
        route_type="duplex",
        platform=PLATFORM_NAME,
        protocol="telegram_bot_api",
        description="Telegram Bot API 双工消息网关（长轮询）",
    )
    async def handle_telegram_gateway(
        self,
        message: Dict[str, Any],
        route: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """处理 Host 出站消息并发送到 Telegram。"""
        del metadata, kwargs

        outbound_codec = self._outbound_codec
        if outbound_codec is None:
            return {"success": False, "error": "Telegram 适配器未初始化"}

        try:
            result = await outbound_codec.send_outbound_message(message, route or {})
        except Exception as exc:
            return {"success": False, "error": str(exc)}

        return result

    def _load_settings(self) -> TelegramPluginSettings:
        return cast(TelegramPluginSettings, self.config)

    async def _restart_if_needed(self) -> None:
        """根据当前配置重启轮询。"""
        settings = self._load_settings()
        await self._stop_polling()

        if not settings.should_connect():
            self.ctx.logger.info("Telegram 适配器保持空闲状态，因为插件未启用")
            return
        if not settings.validate_runtime_config(self.ctx.logger):
            return
        if not TelegramClient.is_available():
            self.ctx.logger.error("Telegram 适配器依赖 aiohttp，但当前环境未安装该依赖")
            return

        # 初始化客户端和编解码器
        bot_cfg = settings.telegram_bot
        self._tg_client = TelegramClient(
            token=bot_cfg.token,
            api_base=bot_cfg.api_base,
            proxy_url=bot_cfg.proxy_url if bot_cfg.proxy_enabled else None,
            proxy_enabled=bot_cfg.proxy_enabled,
            proxy_from_env=bot_cfg.proxy_from_env,
        )
        self._inbound_codec = TelegramInboundCodec(self._tg_client, self.ctx.logger)
        self._outbound_codec = TelegramOutboundCodec(self._tg_client, self.ctx.logger)
        self._chat_filter = TelegramChatFilter(self.ctx.logger)

        # 获取 bot 身份
        try:
            me = await self._tg_client.get_me()
            if me.get("ok") and me.get("result"):
                bot_id = me["result"].get("id")
                bot_username = me["result"].get("username")
                if bot_id:
                    self._inbound_codec.set_self(bot_id, bot_username)
                    self.ctx.logger.info(f"Telegram Bot: id={bot_id}, username={bot_username}")

                    # 上报网关就绪状态
                    await self.ctx.gateway.update_state(
                        gateway_name=TELEGRAM_GATEWAY_NAME,
                        ready=True,
                        platform=PLATFORM_NAME,
                        account_id=str(bot_id),
                    )
            else:
                self.ctx.logger.warning(f"Telegram getMe 失败: {me}")
        except Exception as e:
            self.ctx.logger.warning(f"获取 Telegram Bot 信息失败: {e}")

        # 启动轮询
        self._stop_requested = False
        self._poll_task = asyncio.create_task(self._poll_loop(), name="telegram_adapter.poll")

    async def _stop_polling(self) -> None:
        """停止轮询并清理资源。"""
        self._stop_requested = True

        # 上报网关离线
        try:
            await self.ctx.gateway.update_state(
                gateway_name=TELEGRAM_GATEWAY_NAME,
                ready=False,
                platform=PLATFORM_NAME,
            )
        except Exception:
            pass

        poll_task = self._poll_task
        self._poll_task = None
        if poll_task is not None:
            poll_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await poll_task

        if self._tg_client is not None:
            with contextlib.suppress(Exception):
                await self._tg_client.close()
            self._tg_client = None

    async def _poll_loop(self) -> None:
        """Telegram 长轮询主循环。"""
        offset: Optional[int] = None
        settings = self._load_settings()
        timeout = settings.telegram_bot.poll_timeout
        allowed_updates = ["message", "edited_message"]

        self.ctx.logger.info("Telegram 适配器开始轮询...")

        while not self._stop_requested:
            try:
                tg_client = self._tg_client
                if tg_client is None:
                    break

                resp = await tg_client.get_updates(
                    offset=offset, timeout=timeout, allowed_updates=allowed_updates
                )
                if not resp.get("ok"):
                    self.ctx.logger.warning(f"Telegram getUpdates 失败: {resp}")
                    await asyncio.sleep(1)
                    continue

                for update in resp.get("result", []):
                    offset = update.get("update_id", 0) + 1
                    asyncio.create_task(
                        self._handle_update(update),
                        name="telegram_adapter.handle_update",
                    )
            except asyncio.CancelledError:
                raise
            except Exception as e:
                self.ctx.logger.error(f"Telegram 轮询异常: {e}")
                await asyncio.sleep(2)

    async def _handle_update(self, update: Dict[str, Any]) -> None:
        """处理单个 Telegram Update。"""
        msg = update.get("message") or update.get("edited_message")
        if not msg:
            return

        settings = self._load_settings()
        chat = msg.get("chat", {})
        from_user = msg.get("from", {})
        chat_type = chat.get("type")
        chat_id = str(chat.get("id", ""))
        user_id = str(from_user.get("id", ""))

        if not user_id or not chat_id:
            return

        # 聊天过滤
        if self._chat_filter and not self._chat_filter.check_allow(
            settings.chat, user_id, chat_id, chat_type
        ):
            return

        # 转换为 Host 消息格式
        inbound_codec = self._inbound_codec
        if inbound_codec is None:
            return

        try:
            message_dict = await inbound_codec.build_message_dict(msg)
        except Exception as e:
            self.ctx.logger.error(f"Telegram 消息转换失败: {e}")
            return

        if message_dict is None:
            return

        # 路由到 Host
        try:
            await self.ctx.gateway.route_message(
                gateway_name=TELEGRAM_GATEWAY_NAME,
                message=message_dict,
                external_message_id=str(msg.get("message_id", "")),
            )
        except Exception as e:
            self.ctx.logger.error(f"Telegram 消息路由到 Host 失败: {e}")


def create_plugin() -> TelegramAdapterPlugin:
    """创建插件实例。"""
    return TelegramAdapterPlugin()
