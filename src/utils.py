import base64
from collections import deque
from typing import Generic, Hashable, Optional, TypeVar


TKey = TypeVar("TKey", bound=Hashable)


class SlidingWindowDeduper(Generic[TKey]):
    def __init__(self, window_size: int) -> None:
        self._window_size = max(1, int(window_size))
        self._keys: deque[TKey] = deque(maxlen=self._window_size)
        self._key_set: set[TKey] = set()

    def seen_or_add(self, key: TKey) -> bool:
        if key in self._key_set:
            return True

        evicted: Optional[TKey] = self._keys[0] if len(self._keys) == self._window_size else None
        self._keys.append(key)
        self._key_set.add(key)
        if evicted is not None:
            self._key_set.discard(evicted)
        return False


def to_base64(data: bytes) -> str:
    return base64.b64encode(data).decode("utf-8")


def is_group_chat(chat_type: str) -> bool:
    return chat_type in {"group", "supergroup"}


def pick_username(first_name: Optional[str], last_name: Optional[str], username: Optional[str]) -> str:
    if username:
        return username
    name = (first_name or "") + (f" {last_name}" if last_name else "")
    return name.strip() or "TG用户"
