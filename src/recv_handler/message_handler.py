import time
import re
from typing import Any, Dict, List, Optional, Tuple

from maim_message import (
    UserInfo,
    GroupInfo,
    Seg,
    BaseMessageInfo,
    MessageBase,
    FormatInfo,
)

from ..logger import logger
from ..config import global_config
from ..utils import to_base64, is_group_chat, pick_username
from ..telegram_client import TelegramClient
from .message_sending import message_send_instance


ACCEPT_FORMAT = [
    "text",
    "image",
    "emoji",
    "reply",
    "voice",
    "imageurl",
]


class TelegramUpdateHandler:
    def __init__(self, tg_client: TelegramClient) -> None:
        self.tg = tg_client
        self.bot_id: Optional[int] = None
        self.bot_username: Optional[str] = None

    def set_self(self, bot_id: int, username: Optional[str]) -> None:
        self.bot_id = bot_id
        self.bot_username = username

    async def check_allow_to_chat(self, user_id: int, chat_id: Optional[int], chat_type: str) -> bool:
        if is_group_chat(chat_type):
            if global_config.chat.group_list_type == "whitelist" and chat_id not in global_config.chat.group_list:
                logger.warning("群聊不在聊天白名单中，消息被丢弃")
                return False
            if global_config.chat.group_list_type == "blacklist" and chat_id in global_config.chat.group_list:
                logger.warning("群聊在聊天黑名单中，消息被丢弃")
                return False
        else:
            # Telegram 私聊场景：chat.id 是对端用户 ID；from.id 是实际发送者（可能为 bot 自己）。
            # 访问控制应基于“对端用户”，因此优先使用 chat_id。
            peer_user_id = chat_id if chat_id is not None else user_id
            if (
                global_config.chat.private_list_type == "whitelist"
                and peer_user_id not in global_config.chat.private_list
            ):
                logger.warning("私聊不在聊天白名单中，消息被丢弃")
                return False
            if global_config.chat.private_list_type == "blacklist" and peer_user_id in global_config.chat.private_list:
                logger.warning("私聊在聊天黑名单中，消息被丢弃")
                return False
        if user_id in global_config.chat.ban_user_id:
            logger.warning("用户在全局黑名单中，消息被丢弃")
            return False
        return True

    async def handle_update(self, update: Dict[str, Any]) -> None:
        msg = update.get("message") or update.get("edited_message")
        if not msg:
            return

        message_time = time.time()
        chat = msg.get("chat") or {}
        from_user = msg.get("from") or {}
        chat_type = chat.get("type") or ""
        chat_id = chat.get("id")
        user_id = from_user.get("id")

        if user_id is None or chat_id is None:
            logger.debug(
                f"忽略缺少 user_id/chat_id 的消息: user_id={user_id}, chat_id={chat_id}, chat_type={chat_type}"
            )
            return

        is_from_bot = self.bot_id is not None and user_id == self.bot_id

        if not await self.check_allow_to_chat(user_id, chat_id, chat_type):
            return

        # Build user_info / group_info
        user_info = UserInfo(
            platform=global_config.maibot_server.platform_name,
            user_id=str(user_id),
            user_nickname=pick_username(
                from_user.get("first_name"), from_user.get("last_name"), from_user.get("username")
            ),
            user_cardname=None,
        )
        group_info: Optional[GroupInfo] = None
        if is_group_chat(chat_type):
            group_info = GroupInfo(
                platform=global_config.maibot_server.platform_name,
                group_id=str(chat_id),
                group_name=chat.get("title"),
            )

        format_info = FormatInfo(
            content_format=["text", "image", "emoji"],
            accept_format=ACCEPT_FORMAT,
        )

        seg_list, additional_config = await self._extract_segments(msg)
        if not seg_list:
            logger.warning("处理后消息内容为空")
            return
        if is_from_bot:
            # 不拦截 bot 自发消息；但打标供上游（如需要）区分，避免业务侧误触发循环。
            additional_config["from_bot"] = True

        submit_seg = Seg(type="seglist", data=seg_list)
        message_info = BaseMessageInfo(
            platform=global_config.maibot_server.platform_name,
            message_id=str(msg.get("message_id")),
            time=message_time,
            user_info=user_info,
            group_info=group_info,
            template_info=None,
            format_info=format_info,
            additional_config=additional_config,
        )
        message_base = MessageBase(message_info=message_info, message_segment=submit_seg, raw_message=None)
        logger.info("发送到MaiBot处理信息")
        await message_send_instance.message_send(message_base)

    async def _extract_segments(self, msg: Dict[str, Any]) -> Tuple[List[Seg] | None, Dict[str, Any]]:
        segs: List[Seg] = []
        additional: Dict[str, Any] = {}

        # reply 信息（尽量简化，后续可精细化）
        reply_to = msg.get("reply_to_message")
        if reply_to:
            additional["reply_message_id"] = reply_to.get("message_id")
            # 可选：添加简易文本提示（保留原有最小可行展示）
            reply_uid = reply_to.get("from", {}).get("id")
            reply_name = pick_username(
                reply_to.get("from", {}).get("first_name"),
                reply_to.get("from", {}).get("last_name"),
                reply_to.get("from", {}).get("username"),
            )
            segs.append(Seg(type="text", data=f"[回复<{reply_name}:{reply_uid}>："))
            if reply_to.get("text"):
                segs.append(Seg(type="text", data=reply_to.get("text")))
            segs.append(Seg(type="text", data="]，说："))

        # 文本
        if msg.get("text"):
            segs.append(Seg(type="text", data=msg["text"]))

        # 图片
        photos = msg.get("photo") or []
        if photos:
            # Telegram 返回不同尺寸，取最大
            largest = max(photos, key=lambda p: p.get("file_size", 0))
            file_id = largest.get("file_id")
            if file_id:
                file_path = await self.tg.get_file_path(file_id)
                if file_path:
                    try:
                        file_bytes = await self.tg.download_file_bytes(file_path)
                        segs.append(Seg(type="image", data=to_base64(file_bytes)))
                    except Exception as e:
                        logger.error(f"下载图片失败: {e}")
                        # 降级为占位
                        segs.append(Seg(type="text", data="[图片]"))

        # 贴纸（sticker）
        sticker = msg.get("sticker")
        if sticker:
            try:
                if not (sticker.get("is_animated") or sticker.get("is_video")):
                    file_id = sticker.get("file_id")
                    if file_id:
                        fp = await self.tg.get_file_path(file_id)
                        if fp:
                            data = await self.tg.download_file_bytes(fp)
                            segs.append(Seg(type="emoji", data=to_base64(data)))
                else:
                    segs.append(Seg(type="text", data="[贴纸]"))
            except Exception as e:
                logger.error(f"贴纸处理失败: {e}")

        # 动图（animation）
        animation = msg.get("animation")
        if animation:
            try:
                file_id = animation.get("file_id")
                if file_id:
                    fp = await self.tg.get_file_path(file_id)
                    if fp:
                        data = await self.tg.download_file_bytes(fp)
                        segs.append(Seg(type="emoji", data=to_base64(data)))
            except Exception as e:
                logger.error(f"动图处理失败: {e}")

        # 语音（voice）
        voice = msg.get("voice")
        if voice:
            try:
                file_id = voice.get("file_id")
                if file_id:
                    fp = await self.tg.get_file_path(file_id)
                    if fp:
                        data = await self.tg.download_file_bytes(fp)
                        segs.append(Seg(type="voice", data=to_base64(data)))
            except Exception as e:
                logger.error(f"语音处理失败: {e}")

        # 文档（document）
        document = msg.get("document")
        if document:
            file_name = document.get("file_name") or "文件"
            segs.append(Seg(type="text", data=f"[文件:{file_name}]"))

        # 在群聊中识别 @bot 或回复 bot 的消息，插入 mention_bot 段，便于核心识别
        try:
            if self._is_mentioning_self(msg):
                # 标记被@
                segs.insert(0, Seg(type="mention_bot", data="1"))
                additional["at_bot"] = True
        except Exception:
            pass

        return segs or None, additional

    def _is_mentioning_self(self, msg: Dict[str, Any]) -> bool:
        if self.bot_id is None:
            return False
        # 被回复到 bot
        reply_to = msg.get("reply_to_message")
        if reply_to and reply_to.get("from", {}).get("id") == self.bot_id:
            logger.debug("@识别: 命中 reply_to_message.from.id == bot_id")
            return True
        # @mention in text entities / caption entities
        text = msg.get("text") or ""
        entities = msg.get("entities") or []
        if self._entities_have_self(text, entities):
            logger.debug("@识别: 命中 entities 中的 mention/text_mention/bot_command")
            return True
        caption = msg.get("caption") or ""
        cap_entities = msg.get("caption_entities") or []
        if self._entities_have_self(caption, cap_entities):
            logger.debug("@识别: 命中 caption_entities 中的 mention/text_mention/bot_command")
            return True
        # 实体缺失时兜底纯文本（避免客户端异常导致的偏移问题）
        if self.bot_username:
            pattern = re.compile(rf"@{re.escape(self.bot_username)}\b", re.IGNORECASE)
            if (text and pattern.search(text)) or (caption and pattern.search(caption)):
                logger.debug("@识别: 命中文本兜底 @username 匹配")
                return True
        logger.debug(
            f"@识别: 未命中 | bot_id={self.bot_id} bot_username={self.bot_username} "
            f"text='{text}' entities={entities} caption='{caption}' cap_entities={cap_entities}"
        )
        return False

    def _entities_have_self(self, base_text: str, entities: List[Dict[str, Any]]) -> bool:
        if not entities:
            return False
        uname_lower = (self.bot_username or "").lower()
        for ent in entities:
            etype = ent.get("type")
            if etype == "mention":
                try:
                    offset = int(ent.get("offset", 0))
                    length = int(ent.get("length", 0))
                    token = base_text[offset : offset + length]
                    if uname_lower and token.lower() == f"@{uname_lower}":
                        logger.debug(f"@识别: mention 实体命中 token='{token}'")
                        return True
                except Exception:
                    continue
            elif etype == "bot_command":
                # 处理 /cmd@username 形式
                try:
                    offset = int(ent.get("offset", 0))
                    length = int(ent.get("length", 0))
                    token = base_text[offset : offset + length]
                    if uname_lower and f"@{uname_lower}" in token.lower():
                        logger.debug(f"@识别: bot_command 实体命中 token='{token}'")
                        return True
                except Exception:
                    continue
            elif etype == "text_mention":
                user = ent.get("user") or {}
                if user.get("id") == self.bot_id:
                    logger.debug("@识别: text_mention.user.id 命中 bot_id")
                    return True
        return False
