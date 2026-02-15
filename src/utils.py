import base64
from typing import Optional


def to_base64(data: bytes) -> str:
    return base64.b64encode(data).decode("utf-8")


def is_group_chat(chat_type: str) -> bool:
    return chat_type in {"group", "supergroup"}


def pick_username(first_name: Optional[str], last_name: Optional[str], username: Optional[str]) -> str:
    if username:
        return username
    name = (first_name or "") + (f" {last_name}" if last_name else "")
    return name.strip() or "TG用户"
