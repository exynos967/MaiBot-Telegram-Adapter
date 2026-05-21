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
            if chat_config.group_list_type == "whitelist" and not self._id_matches(chat_id, chat_config.group_list):
                self._logger.debug(
                    f"群聊不在白名单中，消息被丢弃: chat_id={chat_id}, "
                    f"chat_id_aliases={self._id_aliases(chat_id)}, group_list={chat_config.group_list}"
                )
                return False
            if chat_config.group_list_type == "blacklist" and self._id_matches(chat_id, chat_config.group_list):
                self._logger.debug(
                    f"群聊在黑名单中，消息被丢弃: chat_id={chat_id}, "
                    f"chat_id_aliases={self._id_aliases(chat_id)}, group_list={chat_config.group_list}"
                )
                return False
        else:
            if chat_config.private_list_type == "whitelist" and user_id not in chat_config.private_list:
                self._logger.debug(
                    f"私聊不在白名单中，消息被丢弃: user_id={user_id}, private_list={chat_config.private_list}"
                )
                return False
            if chat_config.private_list_type == "blacklist" and user_id in chat_config.private_list:
                self._logger.debug(
                    f"私聊在黑名单中，消息被丢弃: user_id={user_id}, private_list={chat_config.private_list}"
                )
                return False

        if user_id in chat_config.ban_user_id:
            self._logger.debug(f"用户在全局黑名单中，消息被丢弃: user_id={user_id}")
            return False

        return True

    @classmethod
    def _id_matches(cls, chat_id: str, configured_ids: list[str]) -> bool:
        chat_aliases = cls._id_aliases(chat_id)
        return any(cls._id_aliases(configured_id) & chat_aliases for configured_id in configured_ids)

    @staticmethod
    def _id_aliases(chat_id: str) -> set[str]:
        normalized = str(chat_id or "").strip()
        if not normalized:
            return set()

        aliases = {normalized}
        signless = normalized[1:] if normalized.startswith("-") else normalized
        if signless:
            aliases.add(signless)
        if signless.startswith("100") and len(signless) > 3:
            aliases.add(signless[3:])
            aliases.add(f"-100{signless[3:]}")
        elif signless.isdigit():
            aliases.add(f"-100{signless}")
            aliases.add(f"100{signless}")
        return aliases
