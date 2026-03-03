import base64
from typing import Optional

_TOPIC_GROUP_SPLITTER = "::tg-topic::"


def to_base64(data: bytes) -> str:
    return base64.b64encode(data).decode("utf-8")


def is_group_chat(chat_type: Optional[str]) -> bool:
    return chat_type in {"group", "supergroup"}


def pick_username(first_name: Optional[str], last_name: Optional[str], username: Optional[str]) -> str:
    if username:
        return username
    name = (first_name or "") + (f" {last_name}" if last_name else "")
    return name.strip() or "TG用户"


def build_topic_group_id(
    chat_id: int | str,
    message_thread_id: Optional[int] = None,
    direct_messages_topic_id: Optional[int] = None,
) -> str:
    """
    生成用于 MaiBot 会话分流的虚拟 group_id。
    - 无话题时保持原 chat_id，兼容历史会话
    - 有话题时编码成: <chat_id>::tg-topic::mt=<id>&dm=<id>
    """
    base_chat_id = str(chat_id)
    topic_parts = []
    if message_thread_id is not None:
        topic_parts.append(f"mt={message_thread_id}")
    if direct_messages_topic_id is not None:
        topic_parts.append(f"dm={direct_messages_topic_id}")
    if not topic_parts:
        return base_chat_id
    return f"{base_chat_id}{_TOPIC_GROUP_SPLITTER}{'&'.join(topic_parts)}"


def parse_topic_group_id(group_id: int | str) -> tuple[str, Optional[int], Optional[int]]:
    """
    解析虚拟 group_id，返回:
    (raw_chat_id, message_thread_id, direct_messages_topic_id)
    """
    raw_group_id = str(group_id)
    if _TOPIC_GROUP_SPLITTER not in raw_group_id:
        return raw_group_id, None, None

    base_chat_id, topic_payload = raw_group_id.split(_TOPIC_GROUP_SPLITTER, 1)
    message_thread_id: Optional[int] = None
    direct_messages_topic_id: Optional[int] = None

    for part in topic_payload.split("&"):
        if "=" not in part:
            continue
        key, value = part.split("=", 1)
        try:
            parsed_value = int(value)
        except Exception:
            continue
        if key == "mt":
            message_thread_id = parsed_value
        elif key == "dm":
            direct_messages_topic_id = parsed_value

    return base_chat_id, message_thread_id, direct_messages_topic_id
