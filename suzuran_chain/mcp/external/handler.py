import logging
from typing import Any, Dict, List, Optional

from .jsonrpc import JSONRPCRequest, JSONRPCResponse, JSONRPCError

logger = logging.getLogger(__name__)

MCP_PROTOCOL_VERSION = "2025-06-18"


class MCPMethodHandler:
    def __init__(self, internal_server: Any):
        self._server = internal_server
        self._initialized = False
        self._client_capabilities: Dict[str, Any] = {}
        self._server_info = {"name": "suzuran-mcp", "version": "2.0.0"}
        self._method_table = {
            "initialize": self._handle_initialize,
            "ping": self._handle_ping,
            "tools/list": self._handle_tools_list,
            "tools/call": self._handle_tools_call,
            "resources/list": self._handle_resources_list,
            "resources/read": self._handle_resources_read,
            "resources/subscribe": self._handle_resources_subscribe,
            "resources/unsubscribe": self._handle_resources_unsubscribe,
            "prompts/list": self._handle_prompts_list,
            "prompts/get": self._handle_prompts_get,
            "logging/setLevel": self._handle_logging_set_level,
            "completion/complete": self._handle_completion,
        }
        self._subscriptions: Dict[str, List[str]] = {}

    async def handle(self, request: JSONRPCRequest) -> Optional[JSONRPCResponse]:
        handler = self._method_table.get(request.method)
        if handler is None:
            return JSONRPCResponse.error(request.id, JSONRPCError.method_not_found(request.method))

        if request.method != "initialize" and not self._initialized:
            return JSONRPCResponse.error(request.id, JSONRPCError.invalid_request("Server not initialized"))

        try:
            result = await handler(request.params or {})
            return JSONRPCResponse.success(request.id, result)
        except Exception as e:
            logger.error(f"Method {request.method} error: {e}")
            return JSONRPCResponse.error(request.id, JSONRPCError.internal_error(str(e)))

    async def _handle_initialize(self, params: Dict[str, Any]) -> Dict[str, Any]:
        self._client_capabilities = params.get("capabilities", {})
        self._initialized = True
        logger.info(f"MCP client initialized, capabilities: {self._client_capabilities}")

        server_capabilities: Dict[str, Any] = {
            "tools": {"listChanged": True},
            "resources": {"subscribe": True, "listChanged": True},
            "prompts": {"listChanged": True},
            "logging": {},
        }

        return {
            "protocolVersion": MCP_PROTOCOL_VERSION,
            "capabilities": server_capabilities,
            "serverInfo": self._server_info,
        }

    async def _handle_ping(self, params: Dict[str, Any]) -> Dict[str, Any]:
        return {}

    async def _handle_tools_list(self, params: Dict[str, Any]) -> Dict[str, Any]:
        tools = []
        for tool_id, tool in self._server.tool_instances.items():
            tools.append({
                "name": tool.name,
                "description": tool.description,
                "inputSchema": tool.get_parameters_schema() if hasattr(tool, "get_parameters_schema") else {
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
            })

        for rag_id, rag in self._server.rag_instances.items():
            name = rag.name if hasattr(rag, "name") else "wiki_query"
            description = rag.description if hasattr(rag, "description") else "RAG retrieval"
            tools.append({
                "name": name,
                "description": description,
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Search query"},
                    },
                    "required": ["query"],
                },
            })

        return {"tools": tools}

    async def _handle_tools_call(self, params: Dict[str, Any]) -> Dict[str, Any]:
        name = params.get("name", "")
        arguments = params.get("arguments", {})

        for tool_id, tool in self._server.tool_instances.items():
            if tool.name == name:
                try:
                    result = await tool.execute(arguments)
                    return {"content": [{"type": "text", "text": str(result)}]}
                except Exception as e:
                    return {"content": [{"type": "text", "text": f"Error: {e}"}], "isError": True}

        for rag_id, rag in self._server.rag_instances.items():
            rag_name = rag.name if hasattr(rag, "name") else "wiki_query"
            if rag_name == name:
                try:
                    query = arguments.get("query", "")
                    content = await rag.retrieve(query)
                    return {"content": [{"type": "text", "text": content}]}
                except Exception as e:
                    return {"content": [{"type": "text", "text": f"Error: {e}"}], "isError": True}

        return {"content": [{"type": "text", "text": f"Tool not found: {name}"}], "isError": True}

    async def _handle_resources_list(self, params: Dict[str, Any]) -> Dict[str, Any]:
        resources = []
        for rag_id, rag in self._server.rag_instances.items():
            name = rag.name if hasattr(rag, "name") else "wiki"
            resource_type = rag.get_resource_type() if hasattr(rag, "get_resource_type") else "rag"
            resources.append({
                "uri": f"rag://{name}",
                "name": name,
                "description": rag.description if hasattr(rag, "description") else "",
                "mimeType": "text/plain",
            })
        return {"resources": resources}

    async def _handle_resources_read(self, params: Dict[str, Any]) -> Dict[str, Any]:
        uri = params.get("uri", "")
        if not uri.startswith("rag://"):
            return {"contents": [{"uri": uri, "mimeType": "text/plain", "text": "Unsupported resource URI"}]}

        rag_name = uri[6:]
        for rag_id, rag in self._server.rag_instances.items():
            name = rag.name if hasattr(rag, "name") else "wiki"
            if name == rag_name:
                return {"contents": [{"uri": uri, "mimeType": "text/plain", "text": f"Resource: {name} (use tools/call to query)"}]}

        return {"contents": [{"uri": uri, "mimeType": "text/plain", "text": f"Resource not found: {rag_name}"}]}

    async def _handle_resources_subscribe(self, params: Dict[str, Any]) -> Dict[str, Any]:
        uri = params.get("uri", "")
        client_id = params.get("_client_id", "default")
        if uri not in self._subscriptions:
            self._subscriptions[uri] = []
        if client_id not in self._subscriptions[uri]:
            self._subscriptions[uri].append(client_id)
        return {}

    async def _handle_resources_unsubscribe(self, params: Dict[str, Any]) -> Dict[str, Any]:
        uri = params.get("uri", "")
        client_id = params.get("_client_id", "default")
        if uri in self._subscriptions and client_id in self._subscriptions[uri]:
            self._subscriptions[uri].remove(client_id)
        return {}

    async def _handle_prompts_list(self, params: Dict[str, Any]) -> Dict[str, Any]:
        prompts = [
            {
                "name": "minecraft_query",
                "description": "Query Minecraft Wiki for game knowledge",
                "arguments": [
                    {"name": "topic", "description": "The topic to query", "required": True},
                ],
            }
        ]
        return {"prompts": prompts}

    async def _handle_prompts_get(self, params: Dict[str, Any]) -> Dict[str, Any]:
        name = params.get("name", "")
        arguments = params.get("arguments", {})

        if name == "minecraft_query":
            topic = arguments.get("topic", "")
            return {
                "description": f"Query Minecraft Wiki about: {topic}",
                "messages": [
                    {"role": "user", "content": {"type": "text", "text": f"请帮我查询 Minecraft 中关于「{topic}」的信息"}},
                ],
            }

        return {"description": f"Unknown prompt: {name}", "messages": []}

    async def _handle_logging_set_level(self, params: Dict[str, Any]) -> Dict[str, Any]:
        level = params.get("level", "info")
        logger.info(f"MCP client set logging level: {level}")
        return {}

    async def _handle_completion(self, params: Dict[str, Any]) -> Dict[str, Any]:
        ref = params.get("ref", {})
        argument = params.get("argument", {})
        return {"completion": {"values": [], "total": 0, "hasMore": False}}