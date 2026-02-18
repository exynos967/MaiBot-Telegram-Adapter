from typing import Any, List

from maim_message import (
    UserInfo,
    GroupInfo,
    Seg,
    BaseMessageInfo,
    MessageBase,
)

from ..logger import logger
from . import tg_sending


class SendHandler:
    def __init__(self):
        pass

    async def handle_message(self, raw_message_base_dict: dict) -> None:
        raw_message_base: MessageBase = MessageBase.from_dict(raw_message_base_dict)
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

        additional_config = getattr(message_info, "additional_config", None) or {}

        # 优先使用适配器透传的 Telegram chat_id，避免私聊场景被错误路由到 sender_id。
        chat_id: int | str | None = None
        if isinstance(additional_config, dict) and additional_config.get("telegram_chat_id") is not None:
            chat_id = additional_config.get("telegram_chat_id")
        elif group_info and group_info.group_id:
            chat_id = group_info.group_id
        elif user_info and user_info.user_id:
            chat_id = user_info.user_id
        else:
            logger.error("无法识别的消息类型（无目标 chat_id）")
            return

        normalized_chat_id = self._normalize_chat_id(chat_id)
        logger.info(f"准备发送 Telegram 消息: raw_chat_id={chat_id}, normalized_chat_id={normalized_chat_id}")

        # 解析 reply 目标
        reply_to: int | None = self._extract_reply(message_segment, message_info)

        # 扁平化 seglist 后按顺序发送（简单串行，避免复杂聚合）
        payloads = self._recursively_flatten(message_segment)
        if not payloads:
            logger.warning("消息段为空，不发送")
            return

        sent_count = 0
        for seg in payloads:
            try:
                result: dict[str, Any] | None = None
                if seg.type == "text":
                    result = await tg_sending.tg_message_sender.send_text(normalized_chat_id, seg.data, reply_to)
                    reply_to = None  # 仅第一条携带回复
                elif seg.type == "image":
                    result = await tg_sending.tg_message_sender.send_image_base64(normalized_chat_id, seg.data)
                elif seg.type == "imageurl":
                    result = await tg_sending.tg_message_sender.send_image_url(normalized_chat_id, seg.data)
                elif seg.type == "voice":
                    result = await tg_sending.tg_message_sender.send_voice_base64(normalized_chat_id, seg.data)
                elif seg.type == "videourl":
                    result = await tg_sending.tg_message_sender.send_video_url(normalized_chat_id, seg.data)
                elif seg.type == "file":
                    result = await tg_sending.tg_message_sender.send_document_url(normalized_chat_id, seg.data)
                elif seg.type == "emoji":
                    result = await tg_sending.tg_message_sender.send_animation_base64(normalized_chat_id, seg.data)
                else:
                    logger.debug(f"跳过不支持的发送类型: {seg.type}")
                    continue

                if self._is_send_ok(seg.type, normalized_chat_id, result):
                    sent_count += 1
            except Exception:
                logger.exception(f"发送 Telegram 消息异常: chat_id={normalized_chat_id}, seg_type={seg.type}")

        if sent_count == 0:
            logger.warning(f"没有任何消息成功发送到 Telegram: chat_id={normalized_chat_id}")

    def _normalize_chat_id(self, raw_chat_id: int | str | None) -> int | str | None:
        if raw_chat_id is None:
            return None
        if isinstance(raw_chat_id, int):
            return raw_chat_id

        text = str(raw_chat_id).strip()
        if ":" in text:
            _, text = text.rsplit(":", 1)
            text = text.strip()

        try:
            return int(text)
        except (TypeError, ValueError):
            return raw_chat_id

    def _is_send_ok(self, seg_type: str, chat_id: int | str | None, result: dict[str, Any] | None) -> bool:
        if not isinstance(result, dict):
            logger.error(f"Telegram 发送返回异常: chat_id={chat_id}, seg_type={seg_type}, result={result!r}")
            return False

        if result.get("ok"):
            telegram_msg_id = (result.get("result") or {}).get("message_id")
            logger.info(
                f"Telegram 发送成功: chat_id={chat_id}, seg_type={seg_type}, telegram_message_id={telegram_msg_id}"
            )
            return True

        logger.error(
            f"Telegram 发送失败: chat_id={chat_id}, seg_type={seg_type}, "
            f"description={result.get('description')}, raw={result}"
        )
        return False

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
