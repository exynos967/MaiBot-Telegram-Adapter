from dataclasses import dataclass, field
from typing import Literal

from .config_base import ConfigBase

ADAPTER_PLATFORM = "telegram"


@dataclass
class TelegramBotConfig(ConfigBase):
    token: str
    api_base: str = "https://api.telegram.org"
    poll_timeout: int = 20
    allowed_updates: list[str] = field(default_factory=lambda: ["message"])  # noqa: E731
    proxy_enabled: bool = False
    proxy_url: str = ""
    proxy_from_env: bool = False


@dataclass
class MaiBotServerConfig(ConfigBase):
    platform_name: str = field(default=ADAPTER_PLATFORM, init=False)
    host: str = "localhost"
    port: int = 8000


@dataclass
class ChatConfig(ConfigBase):
    group_list_type: Literal["whitelist", "blacklist"] = "whitelist"
    group_list: list[int] = field(default_factory=list)
    private_list_type: Literal["whitelist", "blacklist"] = "whitelist"
    private_list: list[int] = field(default_factory=list)
    ban_user_id: list[int] = field(default_factory=list)


@dataclass
class DebugConfig(ConfigBase):
    level: Literal["TRACE", "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    maim_message_level: Literal["TRACE", "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    to_file: bool = False
    file_path: str = "logs/telegram-adapter.log"
    rotation: str = "10 MB"
    retention: str = "7 days"
    serialize: bool = False
    backtrace: bool = False
    diagnose: bool = False
