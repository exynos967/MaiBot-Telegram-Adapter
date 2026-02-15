from maim_message import MessageBase, Router
from ..logger import logger


class MessageSending:
    """负责把消息发送到MaiBot"""

    maibot_router: Router = None

    async def message_send(self, message_base: MessageBase) -> bool:
        try:
            send_status = await self.maibot_router.send_message(message_base)
            if not send_status:
                raise RuntimeError("可能是路由未正确配置或连接异常")
            return send_status
        except Exception as e:
            logger.error(f"发送消息失败: {str(e)}")
            logger.error("请检查与MaiBot之间的连接")
            return False

    async def send_custom_message(self, custom_message: dict, platform: str, message_type: str) -> bool:
        try:
            await self.maibot_router.send_custom_message(
                platform=platform, message_type_name=message_type, message=custom_message
            )
            return True
        except Exception as e:
            logger.error(f"发送自定义消息失败: {str(e)}")
            logger.error("请检查与MaiBot之间的连接")
            return False


message_send_instance = MessageSending()
