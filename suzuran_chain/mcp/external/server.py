import logging
from typing import Any, Dict, Optional

from .jsonrpc import JSONRPCRequest, JSONRPCResponse, JSONRPCNotification, JSONRPCError
from .handler import MCPMethodHandler
from .transport import BaseTransport, StdioTransport, HTTPTransport

logger = logging.getLogger(__name__)


class MCPServerAdapter:
    def __init__(self, internal_server: Any):
        self._internal_server = internal_server
        self._handler = MCPMethodHandler(internal_server)
        self._transport: Optional[BaseTransport] = None

    async def handle_request(self, request: JSONRPCRequest) -> Optional[JSONRPCResponse]:
        return await self._handler.handle(request)

    def create_stdio_transport(self) -> StdioTransport:
        transport = StdioTransport(self.handle_request)
        self._transport = transport
        return transport

    def create_http_transport(self) -> HTTPTransport:
        transport = HTTPTransport(self.handle_request)
        self._transport = transport
        return transport

    async def start_stdio(self) -> None:
        transport = self.create_stdio_transport()
        await transport.start()

    async def start_http(self) -> HTTPTransport:
        transport = self.create_http_transport()
        await transport.start()
        return transport

    async def stop(self) -> None:
        if self._transport:
            await self._transport.stop()

    async def send_notification(self, notification: JSONRPCNotification) -> None:
        if self._transport:
            await self._transport.send_notification(notification)

    @property
    def is_initialized(self) -> bool:
        return self._handler._initialized

    def get_internal_server(self) -> Any:
        return self._internal_server