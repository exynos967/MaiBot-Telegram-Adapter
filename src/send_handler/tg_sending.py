from typing import Any, Dict, Optional

from maim_message import MessageBase

from ..logger import logger
from ..telegram_client import TelegramClient


class TGMessageSender:
    def __init__(self, client: TelegramClient) -> None:
        self.client = client

    async def send_message_to_telegram(self, action: str, params: Dict[str, Any]) -> Dict[str, Any]:
        # 预留命令通道（例如 future: ban/kick 等）
        return {"status": "error", "message": f"unsupported action: {action}"}

    async def message_sent_back(self, message_base: MessageBase, tg_message_id: int) -> None:
        # 可选：将真实 TG message_id 回传（echo）
        _ = message_base, tg_message_id
        # 暂不回传，后续可扩展：
        # await message_send_instance.send_custom_message({...}, platform, "message_id_echo")

    async def send_text(self, chat_id: int | str, text: str, reply_to: Optional[int] = None) -> Dict[str, Any]:
        return await self.client.send_message(chat_id, text, reply_to)

    async def send_image_base64(self, chat_id: int | str, b64: str, caption: Optional[str] = None) -> Dict[str, Any]:
        import base64

        try:
            image_bytes = base64.b64decode(b64)
        except Exception as e:
            logger.error(f"图片base64解析失败: {e}")
            return {"ok": False, "description": "invalid base64"}
        return await self.client.send_photo_by_bytes(chat_id, image_bytes, caption)

    async def send_image_url(self, chat_id: int | str, url: str, caption: Optional[str] = None) -> Dict[str, Any]:
        return await self.client.send_photo_by_url(chat_id, url, caption)

    async def send_voice_base64(self, chat_id: int | str, b64: str, caption: Optional[str] = None) -> Dict[str, Any]:
        import base64

        try:
            voice_bytes = base64.b64decode(b64)
        except Exception as e:
            logger.error(f"语音base64解析失败: {e}")
            return {"ok": False, "description": "invalid base64"}
        return await self.client.send_voice_by_bytes(chat_id, voice_bytes, caption)

    async def send_video_url(self, chat_id: int | str, url: str, caption: Optional[str] = None) -> Dict[str, Any]:
        return await self.client.send_video_by_url(chat_id, url, caption)

    async def send_document_url(self, chat_id: int | str, url: str, caption: Optional[str] = None) -> Dict[str, Any]:
        return await self.client.send_document_by_url(chat_id, url, caption)

    async def send_animation_base64(
        self, chat_id: int | str, b64: str, caption: Optional[str] = None
    ) -> Dict[str, Any]:
        import base64

        try:
            anim_bytes = base64.b64decode(b64)
        except Exception as e:
            logger.error(f"动图base64解析失败: {e}")
            return {"ok": False, "description": "invalid base64"}
        return await self.client.send_animation_by_bytes(chat_id, anim_bytes, caption)


tg_message_sender: TGMessageSender | None = None
