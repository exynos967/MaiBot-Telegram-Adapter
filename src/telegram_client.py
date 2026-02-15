import asyncio
from typing import Any, Dict, List, Optional

import aiohttp
from urllib.parse import urlparse


class TelegramClient:
    def __init__(
        self,
        token: str,
        api_base: str = "https://api.telegram.org",
        *,
        proxy_url: Optional[str] = None,
        proxy_enabled: bool = False,
        proxy_from_env: bool = False,
    ) -> None:
        self.token = token
        self.api_base = api_base.rstrip("/")
        self._session: Optional[aiohttp.ClientSession] = None
        self._proxy_url: Optional[str] = proxy_url if proxy_enabled and proxy_url else None
        self._proxy_is_socks = self._is_socks(self._proxy_url) if self._proxy_url else False
        self._trust_env: bool = bool(proxy_from_env)

    async def ensure_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=60)
            connector = None
            if self._proxy_is_socks and self._proxy_url:
                try:
                    from aiohttp_socks import ProxyConnector  # type: ignore

                    connector = ProxyConnector.from_url(self._proxy_url)
                except Exception as e:
                    # 不阻断初始化，后续请求会失败并提示
                    print(f"[telegram_client] 警告：SOCKS 代理初始化失败: {e}")
            self._session = aiohttp.ClientSession(timeout=timeout, connector=connector, trust_env=self._trust_env)
        return self._session

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

    def _url(self, method: str) -> str:
        return f"{self.api_base}/bot{self.token}/{method}"

    async def get_me(self) -> Dict[str, Any]:
        session = await self.ensure_session()
        async with session.get(self._url("getMe"), proxy=self._http_proxy()) as resp:
            return await resp.json()

    async def get_updates(
        self,
        offset: Optional[int] = None,
        timeout: int = 20,
        allowed_updates: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        session = await self.ensure_session()
        payload: Dict[str, Any] = {"timeout": timeout}
        if offset is not None:
            payload["offset"] = offset
        if allowed_updates is not None:
            payload["allowed_updates"] = allowed_updates
        async with session.post(
            self._url("getUpdates"), json=payload, proxy=self._http_proxy()
        ) as resp:
            return await resp.json()

    async def get_file_path(self, file_id: str) -> Optional[str]:
        session = await self.ensure_session()
        async with session.post(
            self._url("getFile"), json={"file_id": file_id}, proxy=self._http_proxy()
        ) as resp:
            data = await resp.json()
            if data.get("ok") and data.get("result"):
                return data["result"].get("file_path")
        return None

    async def download_file_bytes(self, file_path: str) -> bytes:
        session = await self.ensure_session()
        # GET https://api.telegram.org/file/bot<token>/<file_path>
        file_url = f"{self.api_base}/file/bot{self.token}/{file_path}"
        async with session.get(file_url, proxy=self._http_proxy()) as resp:
            resp.raise_for_status()
            return await resp.read()

    async def send_message(self, chat_id: int | str, text: str, reply_to: Optional[int] = None) -> Dict[str, Any]:
        session = await self.ensure_session()
        payload: Dict[str, Any] = {"chat_id": chat_id, "text": text}
        if reply_to is not None:
            payload["reply_parameters"] = {"message_id": reply_to}
        async with session.post(
            self._url("sendMessage"), json=payload, proxy=self._http_proxy()
        ) as resp:
            return await resp.json()

    async def send_photo_by_bytes(self, chat_id: int | str, photo_bytes: bytes, caption: Optional[str] = None) -> Dict[str, Any]:
        session = await self.ensure_session()
        form = aiohttp.FormData()
        form.add_field("chat_id", str(chat_id))
        if caption:
            form.add_field("caption", caption)
        form.add_field("photo", photo_bytes, filename="image.jpg", content_type="image/jpeg")
        async with session.post(
            self._url("sendPhoto"), data=form, proxy=self._http_proxy()
        ) as resp:
            return await resp.json()

    async def send_photo_by_url(self, chat_id: int | str, url: str, caption: Optional[str] = None) -> Dict[str, Any]:
        session = await self.ensure_session()
        payload: Dict[str, Any] = {"chat_id": chat_id, "photo": url}
        if caption:
            payload["caption"] = caption
        async with session.post(
            self._url("sendPhoto"), json=payload, proxy=self._http_proxy()
        ) as resp:
            return await resp.json()

    async def send_voice_by_bytes(
        self, chat_id: int | str, voice_bytes: bytes, caption: Optional[str] = None
    ) -> Dict[str, Any]:
        session = await self.ensure_session()
        form = aiohttp.FormData()
        form.add_field("chat_id", str(chat_id))
        if caption:
            form.add_field("caption", caption)
        form.add_field("voice", voice_bytes, filename="voice.ogg", content_type="audio/ogg")
        async with session.post(
            self._url("sendVoice"), data=form, proxy=self._http_proxy()
        ) as resp:
            return await resp.json()

    async def send_video_by_url(self, chat_id: int | str, url: str, caption: Optional[str] = None) -> Dict[str, Any]:
        session = await self.ensure_session()
        payload: Dict[str, Any] = {"chat_id": chat_id, "video": url}
        if caption:
            payload["caption"] = caption
        async with session.post(
            self._url("sendVideo"), json=payload, proxy=self._http_proxy()
        ) as resp:
            return await resp.json()

    async def send_document_by_url(
        self, chat_id: int | str, url: str, caption: Optional[str] = None
    ) -> Dict[str, Any]:
        session = await self.ensure_session()
        payload: Dict[str, Any] = {"chat_id": chat_id, "document": url}
        if caption:
            payload["caption"] = caption
        async with session.post(
            self._url("sendDocument"), json=payload, proxy=self._http_proxy()
        ) as resp:
            return await resp.json()

    async def send_animation_by_bytes(
        self, chat_id: int | str, anim_bytes: bytes, caption: Optional[str] = None
    ) -> Dict[str, Any]:
        session = await self.ensure_session()
        form = aiohttp.FormData()
        form.add_field("chat_id", str(chat_id))
        if caption:
            form.add_field("caption", caption)
        form.add_field("animation", anim_bytes, filename="animation.gif", content_type="image/gif")
        async with session.post(
            self._url("sendAnimation"), data=form, proxy=self._http_proxy()
        ) as resp:
            return await resp.json()

    def _is_socks(self, proxy_url: Optional[str]) -> bool:
        if not proxy_url:
            return False
        try:
            scheme = urlparse(proxy_url).scheme.lower()
            return scheme.startswith("socks")
        except Exception:
            return False

    def _http_proxy(self) -> Optional[str]:
        # aiohttp 支持 per-request `proxy` 仅用于 HTTP(S) 代理；Socks 由 connector 处理
        if self._proxy_url and not self._proxy_is_socks:
            return self._proxy_url
        return None
