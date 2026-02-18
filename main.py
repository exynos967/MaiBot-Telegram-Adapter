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
from src.utils import SlidingWindowDeduper
import src.send_handler.tg_sending as tg_sending


def _positive_int(value: object, default: int) -> int:
    try:
        value_int = int(value)
    except (TypeError, ValueError):
        return default
    return value_int if value_int > 0 else default


def _normalize_allowed_updates(value: object) -> list[str]:
    if not isinstance(value, list):
        return ["message"]
    ret: list[str] = [str(item) for item in value if isinstance(item, str) and item]
    return ret or ["message"]


async def _bootstrap_poll_offset(
    tg: TelegramClient, allowed_updates: list[str], seen_update_deduper: SlidingWindowDeduper[int]
) -> Optional[int]:
    """启动时跳过积压更新，避免历史消息被当作新消息重放。"""
    max_bootstrap_batches = 20
    max_consecutive_invalid_batches = 3
    offset: Optional[int] = None
    max_update_id: Optional[int] = None
    skipped = 0
    batch_count = 0
    consecutive_invalid_batches = 0

    logger.info("初始化 Telegram 轮询 offset...")

    while batch_count < max_bootstrap_batches:
        try:
            resp = await tg.get_updates(offset=offset, timeout=0, allowed_updates=allowed_updates)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("初始化轮询 offset 失败，将从默认 offset 开始轮询")
            return None

        if not resp.get("ok"):
            logger.warning(f"初始化轮询 offset 失败（getUpdates 返回异常）: {resp}")
            return None

        updates = resp.get("result") or []
        if not updates:
            break

        batch_count += 1
        valid_uid_count = 0
        for upd in updates:
            uid_raw = upd.get("update_id")
            try:
                uid = int(uid_raw)
            except (TypeError, ValueError):
                continue
            valid_uid_count += 1
            skipped += 1
            seen_update_deduper.seen_or_add(uid)
            max_update_id = uid if max_update_id is None else max(max_update_id, uid)

        if valid_uid_count == 0:
            consecutive_invalid_batches += 1
            logger.warning(
                "初始化轮询时收到无有效 update_id 的批次，"
                f"consecutive_invalid_batches={consecutive_invalid_batches}"
            )
            if consecutive_invalid_batches >= max_consecutive_invalid_batches:
                logger.warning(
                    "初始化轮询连续收到无有效 update_id 的批次，"
                    "停止继续清积压并开始正常轮询"
                )
                break
            continue
        consecutive_invalid_batches = 0

        if max_update_id is not None:
            offset = max_update_id + 1
            if batch_count % 5 == 0:
                logger.info(f"跳过积压进行中: batches={batch_count}, skipped={skipped}, offset={offset}")

    if batch_count >= max_bootstrap_batches:
        logger.warning(
            f"启动积压更新批次数超过上限({max_bootstrap_batches})，"
            "停止继续清积压并开始正常轮询"
        )

    if max_update_id is None:
        return None

    logger.info(f"启动时检测到 {skipped} 条积压更新，已跳过到 offset={offset}")
    return offset


async def telegram_poll_loop(handler: TelegramUpdateHandler) -> None:
    tg = handler.tg
    offset: Optional[int] = None
    tg_cfg = global_config.telegram_bot
    timeout = _positive_int(getattr(tg_cfg, "poll_timeout", 20), 20)
    allowed = _normalize_allowed_updates(getattr(tg_cfg, "allowed_updates", ["message"]))
    shared_dedup_window = _positive_int(getattr(tg_cfg, "dedup_window", 4096), 4096)
    update_dedup_window_raw = _positive_int(getattr(tg_cfg, "update_dedup_window", 0), 0)
    dedup_window = update_dedup_window_raw if update_dedup_window_raw > 0 else shared_dedup_window
    seen_update_deduper = SlidingWindowDeduper[int](dedup_window)
    logger.info(
        f"启动 Telegram 轮询... timeout={timeout}, allowed_updates={allowed}, update_dedup_window={dedup_window}"
    )
    offset = await _bootstrap_poll_offset(tg, allowed, seen_update_deduper)
    while True:
        try:
            resp = await tg.get_updates(offset=offset, timeout=timeout, allowed_updates=allowed)
            if not resp.get("ok"):
                logger.warning(f"getUpdates失败: {resp}")
                await asyncio.sleep(1)
                continue
            updates = resp.get("result") or []
            for upd in updates:
                uid_raw = upd.get("update_id")
                if uid_raw is None:
                    logger.warning(f"忽略缺少 update_id 的 update: {upd}")
                    continue
                try:
                    uid = int(uid_raw)
                except (TypeError, ValueError):
                    logger.warning(f"忽略非法 update_id={uid_raw!r} 的 update: {upd}")
                    continue

                # 先推进 offset，确保异常或重复场景不会导致同一 update 被持续回放。
                next_offset = uid + 1
                offset = next_offset if offset is None else max(offset, next_offset)

                if seen_update_deduper.seen_or_add(uid):
                    logger.debug(f"跳过重复 update_id={uid}")
                    continue

                try:
                    await handler.handle_update(upd)
                except asyncio.CancelledError:
                    raise
                except Exception:
                    # 避免异常导致 offset 不推进而重复拉取同一 update（上游可能因此判定刷屏）
                    logger.exception(f"处理 update_id={uid} 时异常")
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.exception(f"轮询异常: {e}")
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
                logger.info(
                    f"请确认 MaiBot 的 bot.platforms 包含 telegram:{bot_id}（或 tg:{bot_id}），"
                    "否则机器人自身消息会被识别为普通用户"
                )
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

    def _log_bg_task_result(name: str, task: asyncio.Task) -> None:
        try:
            task.result()
        except asyncio.CancelledError:
            return
        except Exception:
            logger.exception(f"{name} 任务异常退出")

    router_task.add_done_callback(lambda t: _log_bg_task_result("MaiBot 通信", t))
    poll_task.add_done_callback(lambda t: _log_bg_task_result("Telegram 轮询", t))

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
