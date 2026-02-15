from typing import Any, Dict, List

from maim_message import (
    UserInfo,
    GroupInfo,
    Seg,
    BaseMessageInfo,
    MessageBase,
)

from ..logger import logger
from ..config import global_config
from . import tg_sending


class SendHandler:
    def __init__(self):
        pass

    async def handle_message(self, raw_message_base_dict: dict) -> None:
        raw_message_base: MessageBase = MessageBase.from_dict(raw_message_base_dict)
        message_segment: Seg = raw_message_base.message_segment
        logger.info("接收到来自MaiBot的消息，处理中")
        return await self.send_normal_message(raw_message_base)

    async def send_normal_message(self, raw_message_base: MessageBase) -> None:
        if tg_sending.tg_message_sender is None:
            logger.error("Telegram 发送器未初始化")
            return

        message_info: BaseMessageInfo = raw_message_base.message_info
        message_segment: Seg = raw_message_base.message_segment
        group_info: GroupInfo | None = message_info.group_info
        user_info: UserInfo | None = message_info.user_info

        # 确定目标 chat_id
        chat_id: int | str | None = None
        if group_info and group_info.group_id:
            chat_id = group_info.group_id
        elif user_info and user_info.user_id:
            chat_id = user_info.user_id
        else:
            logger.error("无法识别的消息类型（无目标 chat_id）")
            return

        # 解析 reply 目标
        reply_to: int | None = self._extract_reply(message_segment, message_info)

        # 扁平化 seglist 后按顺序发送（简单串行，避免复杂聚合）
        payloads = self._recursively_flatten(message_segment)
        if not payloads:
            logger.warning("消息段为空，不发送")
            return

        for seg in payloads:
            if seg.type == "text":
                await tg_sending.tg_message_sender.send_text(chat_id, seg.data, reply_to)
                reply_to = None  # 仅第一条携带回复
            elif seg.type == "image":
                await tg_sending.tg_message_sender.send_image_base64(chat_id, seg.data)
            elif seg.type == "imageurl":
                await tg_sending.tg_message_sender.send_image_url(chat_id, seg.data)
            elif seg.type == "voice":
                await tg_sending.tg_message_sender.send_voice_base64(chat_id, seg.data)
            elif seg.type == "videourl":
                await tg_sending.tg_message_sender.send_video_url(chat_id, seg.data)
            elif seg.type == "file":
                await tg_sending.tg_message_sender.send_document_url(chat_id, seg.data)
            elif seg.type == "emoji":
                await tg_sending.tg_message_sender.send_animation_base64(chat_id, seg.data)
            else:
                logger.debug(f"跳过不支持的发送类型: {seg.type}")

    def _recursively_flatten(self, seg_data: Seg) -> List[Seg]:
        items: List[Seg] = []
        if seg_data.type == "seglist":
            for s in seg_data.data:
                items.extend(self._recursively_flatten(s))
            return items
        items.append(seg_data)
        return items

    def _extract_reply(self, seg_data: Seg, message_info: BaseMessageInfo) -> int | None:
        # 优先读取 additional_config.reply_message_id，其次读取 Seg(reply)
        additional = getattr(message_info, "additional_config", None) or {}
        reply_id = additional.get("reply_message_id")
        if reply_id:
            try:
                return int(reply_id)
            except Exception:
                return None

        def _walk(seg: Seg) -> int | None:
            if seg.type == "seglist":
                for s in seg.data:
                    rid = _walk(s)
                    if rid:
                        return rid
                return None
            if seg.type == "reply":
                try:
                    return int(seg.data)
                except Exception:
                    return None
            return None

        return _walk(seg_data)


send_handler = SendHandler()
