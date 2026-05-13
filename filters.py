"""Telegram 聊天过滤器。"""

from typing import Any, Optional

from .config import TelegramChatConfig
from .utils import is_group_chat


class TelegramChatFilter:
    """根据配置过滤入站消息。"""

    def __init__(self, logger: Any) -> None:
        self._logger = logger

    def check_allow(
        self,
        chat_config: TelegramChatConfig,
        user_id: str,
        chat_id: Optional[str],
        chat_type: Optional[str],
    ) -> bool:
        """检查消息是否通过聊天过滤。"""
        if is_group_chat(chat_type) and chat_id:
            if chat_config.group_list_type == "whitelist" and chat_id not in chat_config.group_list:
                self._logger.debug("群聊不在白名单中，消息被丢弃")
                return False
            if chat_config.group_list_type == "blacklist" and chat_id in chat_config.group_list:
                self._logger.debug("群聊在黑名单中，消息被丢弃")
                return False
        else:
            if chat_config.private_list_type == "whitelist" and user_id not in chat_config.private_list:
                self._logger.debug("私聊不在白名单中，消息被丢弃")
                return False
            if chat_config.private_list_type == "blacklist" and user_id in chat_config.private_list:
                self._logger.debug("私聊在黑名单中，消息被丢弃")
                return False

        if user_id in chat_config.ban_user_id:
            self._logger.debug("用户在全局黑名单中，消息被丢弃")
            return False

        return True
