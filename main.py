import asyncio
import signal
from typing import Optional

from src.logger import logger
from src.config import global_config
from src.telegram_client import TelegramClient
from src.mmc_com_layer import mmc_start_com, mmc_stop_com, router
from src.recv_handler.message_sending import message_send_instance
from src.recv_handler.message_handler import TelegramUpdateHandler
from src.send_handler.tg_sending import TGMessageSender
import src.send_handler.tg_sending as tg_sending


async def telegram_poll_loop(handler: TelegramUpdateHandler) -> None:
    tg = handler.tg
    offset: Optional[int] = None
    timeout = global_config.telegram_bot.poll_timeout
    allowed = global_config.telegram_bot.allowed_updates
    logger.info("启动 Telegram 轮询...")
    while True:
        try:
            resp = await tg.get_updates(offset=offset, timeout=timeout, allowed_updates=allowed)
            if not resp.get("ok"):
                logger.warning(f"getUpdates失败: {resp}")
                await asyncio.sleep(1)
                continue
            for upd in resp.get("result", []):
                offset = upd.get("update_id", 0) + 1
                await handler.handle_update(upd)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"轮询异常: {e}")
            await asyncio.sleep(2)


async def main() -> None:
    # wire up dependencies
    tg_cfg = global_config.telegram_bot
    tg_client = TelegramClient(
        tg_cfg.token,
        tg_cfg.api_base,
        proxy_url=(tg_cfg.proxy_url if tg_cfg.proxy_enabled and tg_cfg.proxy_url else None),
        proxy_enabled=tg_cfg.proxy_enabled,
        proxy_from_env=tg_cfg.proxy_from_env,
    )
    handler = TelegramUpdateHandler(tg_client)
    # 获取机器人身份，便于识别 @bot 或回复 bot
    try:
        me = await tg_client.get_me()
        if me.get("ok") and me.get("result"):
            bot_id = me["result"].get("id")
            bot_username = me["result"].get("username")
            if bot_id:
                handler.set_self(bot_id, bot_username)
                logger.info(f"Telegram Self: id={bot_id}, username={bot_username}")
        else:
            logger.warning(f"getMe 失败: {me}")
    except Exception as e:
        logger.warning(f"获取 Telegram 自身信息失败: {e}")

    # bind sender
    # 设置模块级发送器实例，供接收的 handler 读取
    tg_sending.tg_message_sender = TGMessageSender(tg_client)
    message_send_instance.maibot_router = router

    # start MaiBot router and TG polling
    router_task = asyncio.create_task(mmc_start_com())
    poll_task = asyncio.create_task(telegram_poll_loop(handler))

    # graceful shutdown on signals
    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()

    def _handle_signal():
        logger.warning("收到停止信号，准备关闭...")
        stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _handle_signal)
        except NotImplementedError:
            # Windows may not support all signals in asyncio
            pass

    await stop_event.wait()
    for t in (poll_task, router_task):
        t.cancel()
    await asyncio.gather(*[router_task, poll_task], return_exceptions=True)
    # 关闭通信路由与 Telegram 客户端，吞掉取消异常，避免退出时噪声栈
    try:
        await mmc_stop_com()
    except asyncio.CancelledError:
        pass
    except Exception as e:
        logger.exception(f"停止 MaiBot 通信时出现异常: {e}")

    try:
        await tg_client.close()
    except asyncio.CancelledError:
        pass
    except Exception as e:
        logger.exception(f"关闭 Telegram 客户端失败: {e}")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
