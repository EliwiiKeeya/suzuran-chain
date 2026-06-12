import json
import asyncio
import logging
from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, List, Optional
from .jsonrpc import JSONRPCRequest, JSONRPCResponse, JSONRPCNotification, JSONRPCError

logger = logging.getLogger(__name__)


class BaseTransport(ABC):
    def __init__(self, handler: Callable[[JSONRPCRequest], Optional[JSONRPCResponse]]):
        self._handler = handler
        self._notification_handlers: Dict[str, List[Callable]] = {}

    @abstractmethod
    async def start(self) -> None:
        pass

    @abstractmethod
    async def stop(self) -> None:
        pass

    def on_notification(self, method: str, callback: Callable) -> None:
        if method not in self._notification_handlers:
            self._notification_handlers[method] = []
        self._notification_handlers[method].append(callback)

    async def send_notification(self, notification: JSONRPCNotification) -> None:
        pass

    async def _process_message(self, raw: str) -> Optional[str]:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            response = JSONRPCResponse.error(None, JSONRPCError.parse_error())
            return response.to_json()

        is_batch = isinstance(data, list)
        if is_batch:
            results = []
            for item in data:
                r = await self._process_single(item)
                if r is not None:
                    results.append(json.loads(r))
            return json.dumps(results) if results else None

        return await self._process_single(data)

    async def _process_single(self, data: Dict[str, Any]) -> Optional[str]:
        if data.get("method") and "id" not in data:
            notification = JSONRPCNotification(
                method=data["method"],
                params=data.get("params"),
            )
            handlers = self._notification_handlers.get(notification.method, [])
            for h in handlers:
                try:
                    await h(notification)
                except Exception as e:
                    logger.error(f"Notification handler error: {e}")
            return None

        try:
            request = JSONRPCRequest.from_dict(data)
        except Exception:
            response = JSONRPCResponse.error(None, JSONRPCError.invalid_request())
            return response.to_json()

        if not request.method:
            response = JSONRPCResponse.error(request.id, JSONRPCError.invalid_request())
            return response.to_json()

        try:
            response = await self._handler(request)
            if response is not None:
                return response.to_json()
        except Exception as e:
            logger.error(f"Handler error: {e}")
            response = JSONRPCResponse.error(request.id, JSONRPCError.internal_error(str(e)))
            return response.to_json()

        return None


class StdioTransport(BaseTransport):
    async def start(self) -> None:
        logger.info("[StdioTransport] Starting")
        loop = asyncio.get_event_loop()
        try:
            while True:
                line = await loop.run_in_executor(None, input)
                line = line.strip()
                if not line:
                    continue
                result = await self._process_message(line)
                if result is not None:
                    print(result, flush=True)
        except EOFError:
            pass

    async def stop(self) -> None:
        logger.info("[StdioTransport] Stopped")


class HTTPTransport(BaseTransport):
    def __init__(self, handler: Callable[[JSONRPCRequest], Optional[JSONRPCResponse]]):
        super().__init__(handler)
        self._sse_clients: List[Any] = []

    async def start(self) -> None:
        logger.info("[HTTPTransport] Ready (requires FastAPI integration)")

    async def stop(self) -> None:
        self._sse_clients.clear()
        logger.info("[HTTPTransport] Stopped")

    async def handle_post(self, raw_body: str) -> str:
        result = await self._process_message(raw_body)
        return result or ""

    async def send_notification(self, notification: JSONRPCNotification) -> None:
        payload = notification.to_json()
        disconnected = []
        for i, queue in enumerate(self._sse_clients):
            try:
                await queue.put(payload)
            except Exception:
                disconnected.append(i)
        for i in reversed(disconnected):
            self._sse_clients.pop(i)

    def register_sse_client(self, queue: asyncio.Queue) -> None:
        self._sse_clients.append(queue)

    def unregister_sse_client(self, queue: asyncio.Queue) -> None:
        try:
            self._sse_clients.remove(queue)
        except ValueError:
            pass