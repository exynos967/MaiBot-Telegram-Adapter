"""Telegram 适配器配置模型。"""

from __future__ import annotations

from typing import Any, ClassVar, List, Literal

from maibot_sdk import Field, PluginConfigBase
from pydantic import field_validator

from .constants import (
    DEFAULT_API_BASE,
    DEFAULT_CHAT_LIST_TYPE,
    DEFAULT_POLL_TIMEOUT,
    SUPPORTED_CONFIG_VERSION,
)


class TelegramPluginOptions(PluginConfigBase):
    """插件级配置。"""

    __ui_label__: ClassVar[str] = "插件设置"
    __ui_order__: ClassVar[int] = 0

    enabled: bool = Field(
        default=False,
        description="是否启用 Telegram 适配器。",
        json_schema_extra={
            "hint": "关闭后插件会保持空闲，不会启动 Telegram 轮询。",
            "label": "启用适配器",
            "order": 0,
        },
    )
    config_version: str = Field(
        default=SUPPORTED_CONFIG_VERSION,
        description="当前配置结构版本。",
        json_schema_extra={"disabled": True, "hidden": True, "label": "配置版本", "order": 99},
    )


class TelegramBotConfig(PluginConfigBase):
    """Telegram Bot 连接配置。"""

    __ui_label__: ClassVar[str] = "Telegram Bot"
    __ui_order__: ClassVar[int] = 1

    token: str = Field(
        default="",
        description="Telegram Bot Token，从 @BotFather 获取。",
        json_schema_extra={
            "input_type": "password",
            "label": "Bot Token",
            "order": 0,
            "placeholder": "123456:ABC-DEF...",
        },
    )
    api_base: str = Field(
        default=DEFAULT_API_BASE,
        description="Telegram Bot API 基础地址。",
        json_schema_extra={
            "hint": "如使用自建 API 服务器可修改此项。",
            "label": "API 地址",
            "order": 1,
            "placeholder": "https://api.telegram.org",
        },
    )
    poll_timeout: int = Field(
        default=DEFAULT_POLL_TIMEOUT,
        description="长轮询超时时间（秒）。",
        json_schema_extra={"label": "轮询超时（秒）", "order": 2, "step": 1},
    )
    proxy_enabled: bool = Field(
        default=False,
        description="是否启用代理。",
        json_schema_extra={"label": "启用代理", "order": 3},
    )
    proxy_url: str = Field(
        default="",
        description="代理地址（HTTP/SOCKS5）。",
        json_schema_extra={
            "hint": "支持 http:// 和 socks5:// 协议。",
            "label": "代理地址",
            "order": 4,
            "placeholder": "http://127.0.0.1:7890",
        },
    )
    proxy_from_env: bool = Field(
        default=False,
        description="是否从环境变量读取代理。",
        json_schema_extra={"label": "从环境变量读取代理", "order": 5},
    )

    @field_validator("token", "api_base", "proxy_url", mode="before")
    @classmethod
    def _normalize_text(cls, value: Any) -> str:
        return "" if value is None else str(value).strip()

    @field_validator("poll_timeout", mode="before")
    @classmethod
    def _normalize_poll_timeout(cls, value: Any) -> int:
        try:
            v = int(value)
            return v if v > 0 else DEFAULT_POLL_TIMEOUT
        except (TypeError, ValueError):
            return DEFAULT_POLL_TIMEOUT


class TelegramChatConfig(PluginConfigBase):
    """聊天名单配置。"""

    __ui_label__: ClassVar[str] = "聊天过滤"
    __ui_order__: ClassVar[int] = 2

    group_list_type: Literal["whitelist", "blacklist"] = Field(
        default=DEFAULT_CHAT_LIST_TYPE,
        description="群聊名单模式。",
        json_schema_extra={"label": "群聊名单模式", "order": 0},
    )
    group_list: List[str] = Field(
        default_factory=list,
        description="群聊名单中的 chat_id 列表。",
        json_schema_extra={"label": "群聊名单", "order": 1, "placeholder": "请输入 chat_id"},
    )
    private_list_type: Literal["whitelist", "blacklist"] = Field(
        default=DEFAULT_CHAT_LIST_TYPE,
        description="私聊名单模式。",
        json_schema_extra={"label": "私聊名单模式", "order": 2},
    )
    private_list: List[str] = Field(
        default_factory=list,
        description="私聊名单中的用户 ID 列表。",
        json_schema_extra={"label": "私聊名单", "order": 3, "placeholder": "请输入用户 ID"},
    )
    ban_user_id: List[str] = Field(
        default_factory=list,
        description="全局屏蔽的用户 ID 列表。",
        json_schema_extra={"label": "全局屏蔽用户", "order": 4, "placeholder": "请输入用户 ID"},
    )

    @field_validator("group_list_type", "private_list_type", mode="before")
    @classmethod
    def _normalize_list_type(cls, value: Any) -> str:
        v = str(value or "").strip().lower()
        return v if v in ("whitelist", "blacklist") else DEFAULT_CHAT_LIST_TYPE

    @field_validator("group_list", "private_list", "ban_user_id", mode="before")
    @classmethod
    def _normalize_id_lists(cls, value: Any) -> List[str]:
        if not isinstance(value, list):
            return []
        seen: set[str] = set()
        result: List[str] = []
        for item in value:
            s = str(item).strip()
            if s and s not in seen:
                seen.add(s)
                result.append(s)
        return result


class TelegramPluginSettings(PluginConfigBase):
    """Telegram 插件完整配置。"""

    plugin: TelegramPluginOptions = Field(default_factory=TelegramPluginOptions)
    telegram_bot: TelegramBotConfig = Field(default_factory=TelegramBotConfig)
    chat: TelegramChatConfig = Field(default_factory=TelegramChatConfig)

    def should_connect(self) -> bool:
        return self.plugin.enabled

    def validate_runtime_config(self, logger: Any) -> bool:
        if not self.telegram_bot.token:
            logger.warning("Telegram 适配器已启用，但 telegram_bot.token 为空")
            return False
        return True
