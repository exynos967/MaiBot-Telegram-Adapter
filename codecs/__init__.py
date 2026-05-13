"""Telegram 入站消息编解码：将 Telegram Update 转换为 Host 侧 MessageDict。"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import hashlib
import re
import time

from ..constants import PLATFORM_NAME
from ..telegram_client import TelegramClient
from ..utils import build_topic_group_id, is_group_chat, pick_username, slice_by_utf16_units


class TelegramInboundCodec:
    """将 Telegram 消息转换为 Host 侧标准 MessageDict。"""

    def __init__(self, tg_client: TelegramClient, logger: Any) -> None:
        self._tg = tg_client
        self._logger = logger
        self._bot_id: Optional[int] = None
        self._bot_username: Optional[str] = None

    def set_self(self, bot_id: int, username: Optional[str]) -> None:
        self._bot_id = bot_id
        self._bot_username = username

    async def build_message_dict(self, msg: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """将 Telegram message 对象转换为 Host 侧 MessageDict。

        Returns:
            None 表示消息不可处理或内容为空。
        """
        chat = msg.get("chat", {})
        from_user = msg.get("from", {})
        chat_type = chat.get("type")
        chat_id = chat.get("id")
        user_id = from_user.get("id")
        message_thread_id = msg.get("message_thread_id")
        direct_messages_topic_id = msg.get("direct_messages_topic_id")

        if user_id is None or chat_id is None:
            return None

        sender_user_id = str(user_id)
        user_nickname = pick_username(
            from_user.get("first_name"), from_user.get("last_name"), from_user.get("username")
        )

        # 构建消息段
        segments, additional_config, is_at = await self._extract_segments(msg)
        if not segments:
            return None

        # 构建 message_info
        message_info: Dict[str, Any] = {
            "user_info": {
                "platform": PLATFORM_NAME,
                "user_id": sender_user_id,
                "user_nickname": user_nickname,
                "user_cardname": None,
            },
            "additional_config": additional_config,
        }

        # 群聊信息
        if is_group_chat(chat_type):
            virtual_group_id = build_topic_group_id(chat_id, message_thread_id, direct_messages_topic_id)
            additional_config["platform_io_target_group_id"] = virtual_group_id
            message_info["group_info"] = {
                "group_id": virtual_group_id,
                "group_name": chat.get("title") or f"group_{chat_id}",
            }
        else:
            # 私聊：设置 platform_io_target_user_id
            additional_config["platform_io_target_user_id"] = sender_user_id

        # 构建完整的 plain_text
        plain_text = "".join(
            seg.get("data", "") for seg in segments if seg.get("type") == "text"
        )

        # 判断是否包含图片/emoji
        has_image = any(seg.get("type") == "image" for seg in segments)
        has_emoji = any(seg.get("type") == "emoji" for seg in segments)

        message_id = str(msg.get("message_id") or f"tg-{int(time.time() * 1000)}")

        return {
            "message_id": message_id,
            "timestamp": str(time.time()),
            "platform": PLATFORM_NAME,
            "message_info": message_info,
            "raw_message": segments,
            "is_mentioned": is_at,
            "is_at": is_at,
            "is_emoji": has_emoji,
            "is_picture": has_image,
            "is_command": plain_text.startswith("/"),
            "is_notify": False,
            "processed_plain_text": plain_text,
        }

    async def _extract_segments(self, msg: Dict[str, Any]) -> Tuple[Optional[List[Dict[str, Any]]], Dict[str, Any], bool]:
        """从 Telegram 消息中提取消息段列表。

        Returns:
            (segments, additional_config, is_at)
        """
        segs: List[Dict[str, Any]] = []
        additional: Dict[str, Any] = {}
        is_at = False

        # 保留 topic 信息
        if msg.get("message_thread_id") is not None:
            additional["message_thread_id"] = msg["message_thread_id"]
        if msg.get("direct_messages_topic_id") is not None:
            additional["direct_messages_topic_id"] = msg["direct_messages_topic_id"]

        # 回复信息
        reply_to = msg.get("reply_to_message")
        if reply_to:
            additional["reply_message_id"] = reply_to.get("message_id")
            reply_name = pick_username(
                reply_to.get("from", {}).get("first_name"),
                reply_to.get("from", {}).get("last_name"),
                reply_to.get("from", {}).get("username"),
            )
            reply_uid = reply_to.get("from", {}).get("id")
            segs.append({"type": "text", "data": f"[回复<{reply_name}:{reply_uid}>："})
            if reply_to.get("text"):
                segs.append({"type": "text", "data": reply_to["text"]})
            segs.append({"type": "text", "data": "]，说："})

        # 文本
        if msg.get("text"):
            segs.append({"type": "text", "data": msg["text"]})
        if msg.get("caption"):
            segs.append({"type": "text", "data": msg["caption"]})

        # 图片
        photos = msg.get("photo") or []
        if photos:
            largest = max(photos, key=lambda p: p.get("file_size", 0))
            file_id = largest.get("file_id")
            if file_id:
                raw_bytes = await self._download_file_bytes(file_id)
                if raw_bytes:
                    segs.append(self._build_binary_segment("image", raw_bytes))
                else:
                    segs.append({"type": "text", "data": "[图片]"})

        # 贴纸
        sticker = msg.get("sticker")
        if sticker:
            if not (sticker.get("is_animated") or sticker.get("is_video")):
                raw_bytes = await self._download_file_bytes(sticker.get("file_id"))
                if raw_bytes:
                    segs.append(self._build_binary_segment("emoji", raw_bytes))
                else:
                    segs.append({"type": "text", "data": "[贴纸]"})
            else:
                segs.append({"type": "text", "data": "[贴纸]"})

        # 动图
        animation = msg.get("animation")
        if animation:
            raw_bytes = await self._download_file_bytes(animation.get("file_id"))
            if raw_bytes:
                segs.append(self._build_binary_segment("emoji", raw_bytes))

        # 语音
        voice = msg.get("voice")
        if voice:
            raw_bytes = await self._download_file_bytes(voice.get("file_id"))
            if raw_bytes:
                segs.append(self._build_binary_segment("voice", raw_bytes))

        # 文档
        document = msg.get("document")
        if document:
            file_name = document.get("file_name") or "文件"
            segs.append({"type": "text", "data": f"[文件:{file_name}]"})

        # @bot 识别
        if self._is_mentioning_self(msg):
            bot_id = str(self._bot_id) if self._bot_id is not None else ""
            segs.insert(
                0,
                {
                    "type": "at",
                    "data": {
                        "target_user_id": bot_id,
                        "target_user_nickname": self._bot_username,
                    },
                },
            )
            additional["at_bot"] = True
            is_at = True

        return segs or None, additional, is_at

    async def _download_file_bytes(self, file_id: Optional[str]) -> Optional[bytes]:
        """下载文件并返回原始字节。"""
        if not file_id:
            return None
        try:
            file_path = await self._tg.get_file_path(file_id)
            if file_path:
                return await self._tg.download_file_bytes(file_path)
        except Exception as e:
            self._logger.warning(f"Telegram 文件下载失败: {e}")
        return None

    @staticmethod
    def _build_binary_segment(seg_type: str, raw_bytes: bytes) -> Dict[str, Any]:
        """构造符合 Host 规范的二进制组件段。"""
        import base64
        return {
            "type": seg_type,
            "data": "",
            "hash": hashlib.sha256(raw_bytes).hexdigest(),
            "binary_data_base64": base64.b64encode(raw_bytes).decode("utf-8"),
        }

    def _is_mentioning_self(self, msg: Dict[str, Any]) -> bool:
        """判断消息是否 @bot 或回复 bot。"""
        if self._bot_id is None:
            return False

        # 被回复
        reply_to = msg.get("reply_to_message")
        if reply_to and reply_to.get("from", {}).get("id") == self._bot_id:
            return True

        # entities 中的 mention
        text = msg.get("text") or ""
        entities = msg.get("entities") or []
        if self._entities_have_self(text, entities):
            return True

        caption = msg.get("caption") or ""
        cap_entities = msg.get("caption_entities") or []
        if self._entities_have_self(caption, cap_entities):
            return True

        # 兜底文本匹配
        if self._bot_username:
            pattern = re.compile(rf"@{re.escape(self._bot_username)}\b", re.IGNORECASE)
            if (text and pattern.search(text)) or (caption and pattern.search(caption)):
                return True

        return False

    def _entities_have_self(self, base_text: str, entities: List[Dict[str, Any]]) -> bool:
        if not entities:
            return False
        uname_lower = (self._bot_username or "").lower()
        for ent in entities:
            etype = ent.get("type")
            if etype == "mention":
                try:
                    offset = int(ent.get("offset", 0))
                    length = int(ent.get("length", 0))
                    token = slice_by_utf16_units(base_text, offset, length)
                    if uname_lower and token.lower() == f"@{uname_lower}":
                        return True
                except (TypeError, ValueError):
                    continue
            elif etype == "bot_command":
                try:
                    offset = int(ent.get("offset", 0))
                    length = int(ent.get("length", 0))
                    token = slice_by_utf16_units(base_text, offset, length)
                    if uname_lower and f"@{uname_lower}" in token.lower():
                        return True
                except (TypeError, ValueError):
                    continue
            elif etype == "text_mention":
                user = ent.get("user") or {}
                if user.get("id") == self._bot_id:
                    return True
        return False
