"""Telegram 出站消息编解码：将 Host 侧 MessageDict 转换为 Telegram 发送动作。"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import base64

from ..telegram_client import TelegramClient
from ..utils import parse_topic_group_id


class TelegramOutboundCodec:
    """将 Host 出站消息转换为 Telegram API 调用。"""

    def __init__(self, tg_client: TelegramClient, logger: Any) -> None:
        self._tg = tg_client
        self._logger = logger

    async def send_outbound_message(
        self, message: Dict[str, Any], route: Dict[str, Any]
    ) -> Dict[str, Any]:
        """处理 Host 出站消息并发送到 Telegram。

        Returns:
            标准化发送结果 dict。
        """
        message_info = message.get("message_info", {})
        raw_message = message.get("raw_message", [])
        group_info = message_info.get("group_info")
        user_info = message_info.get("user_info")
        additional_config = message_info.get("additional_config", {})

        # 确定目标 chat_id
        chat_id: Optional[str] = None
        parsed_thread_id: Optional[int] = None
        parsed_dm_topic_id: Optional[int] = None

        if group_info and group_info.get("group_id"):
            chat_id, parsed_thread_id, parsed_dm_topic_id = parse_topic_group_id(group_info["group_id"])
        elif user_info and user_info.get("user_id"):
            chat_id = user_info["user_id"]

        if not chat_id:
            return {"success": False, "error": "无法确定目标 chat_id"}

        # 解析 reply_to
        reply_to = self._extract_reply_to_from_additional(additional_config, raw_message)

        # 解析 topic
        message_thread_id = self._safe_int(additional_config.get("message_thread_id"))
        direct_messages_topic_id = self._safe_int(additional_config.get("direct_messages_topic_id"))
        if message_thread_id is None:
            message_thread_id = parsed_thread_id
        if direct_messages_topic_id is None:
            direct_messages_topic_id = parsed_dm_topic_id

        # raw_message 是组件列表，直接使用
        payloads = raw_message if isinstance(raw_message, list) else []
        if not payloads:
            return {"success": False, "error": "消息段为空"}

        last_result: Dict[str, Any] = {}
        replied = False
        for seg in payloads:
            current_reply = None if replied else reply_to
            result = await self._send_segment(
                chat_id, seg, current_reply, message_thread_id, direct_messages_topic_id
            )
            if result.get("ok"):
                replied = True
                last_result = result

        if not replied:
            return {"success": False, "error": "所有消息段发送失败"}

        # 提取外部消息 ID
        external_id = ""
        result_data = last_result.get("result", {})
        if isinstance(result_data, dict):
            external_id = str(result_data.get("message_id", ""))

        return {"success": True, "external_message_id": external_id or None}

    async def _send_segment(
        self,
        chat_id: str,
        seg: Dict[str, Any],
        reply_to: Optional[int],
        message_thread_id: Optional[int],
        direct_messages_topic_id: Optional[int],
    ) -> Dict[str, Any]:
        """发送单个消息段。"""
        seg_type = str(seg.get("type") or "").strip()
        seg_data = seg.get("data", "")
        # 二进制组件的实际 base64 数据在 binary_data_base64 字段
        binary_b64 = seg.get("binary_data_base64", "")

        try:
            if seg_type == "text":
                text = seg_data if isinstance(seg_data, str) else str(seg_data)
                if not text.strip():
                    return {"ok": False}
                return await self._tg.send_message(
                    chat_id, text, reply_to, message_thread_id, direct_messages_topic_id
                )
            elif seg_type == "image":
                if binary_b64:
                    image_bytes = base64.b64decode(binary_b64)
                    return await self._tg.send_photo_bytes(
                        chat_id, image_bytes, reply_to=reply_to,
                        message_thread_id=message_thread_id,
                        direct_messages_topic_id=direct_messages_topic_id,
                    )
                elif isinstance(seg_data, str) and seg_data.startswith("http"):
                    return await self._tg.send_photo_url(
                        chat_id, seg_data, reply_to=reply_to,
                        message_thread_id=message_thread_id,
                        direct_messages_topic_id=direct_messages_topic_id,
                    )
                return {"ok": False}
            elif seg_type == "voice":
                if binary_b64:
                    voice_bytes = base64.b64decode(binary_b64)
                    return await self._tg.send_voice_bytes(
                        chat_id, voice_bytes, reply_to=reply_to,
                        message_thread_id=message_thread_id,
                        direct_messages_topic_id=direct_messages_topic_id,
                    )
                return {"ok": False}
            elif seg_type == "emoji":
                if binary_b64:
                    anim_bytes = base64.b64decode(binary_b64)
                    return await self._tg.send_animation_bytes(
                        chat_id, anim_bytes, reply_to=reply_to,
                        message_thread_id=message_thread_id,
                        direct_messages_topic_id=direct_messages_topic_id,
                    )
                return {"ok": False}
            elif seg_type in ("reply", "at", "forward", "dict"):
                # 这些类型不需要发送到 Telegram
                return {"ok": False}
            else:
                if seg_type:
                    self._logger.debug(f"跳过不支持的发送类型: {seg_type}")
                return {"ok": False}
        except Exception as e:
            self._logger.warning(f"Telegram 发送 {seg_type} 失败: {e}")
            return {"ok": False, "description": str(e)}

    def _extract_reply_to_from_additional(
        self, additional: Dict[str, Any], raw_message: List[Dict[str, Any]]
    ) -> Optional[int]:
        """提取回复目标消息 ID。"""
        reply_id = additional.get("reply_message_id")
        if reply_id:
            return self._safe_int(reply_id)

        # 从 raw_message 中查找 reply 类型组件
        for seg in raw_message:
            if isinstance(seg, dict) and seg.get("type") == "reply":
                data = seg.get("data")
                if isinstance(data, dict):
                    return self._safe_int(data.get("target_message_id"))
                return self._safe_int(data)
        return None

    @staticmethod
    def _safe_int(value: Any) -> Optional[int]:
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None
