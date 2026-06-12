from typing import Dict, Any, Optional, List, TYPE_CHECKING
from abc import ABC
import uuid

# 导入协议层
from ..mcp.protocol import Role as BaseRole, Resource, MCPMessage, MessageSource, MessagePayload, Adapter

if TYPE_CHECKING:
    from ..mcp.server import MCPServer


class LLMAdapter(Adapter):
    """
    LLM 适配器

    功能：
    1. 解析 MCP 消息中的 tools → OpenAI tools 格式
    2. 解析 MCP 消息中的 resources → 注入到 messages
    3. 解析 MCP 消息中的 rag → 作为 tool_call 处理
    4. 将 LLM 响应包装回 MCP 协议格式
    """

    def __init__(self, llm: "BaseLLM"):
        self._llm = llm

    def _register(self, server: "MCPServer") -> bool:
        """
        注册 LLM 到 MCP Server
        
        注意：此方法由 RoleManager 自动调用，不应该再次调用 server.register_role
        因为角色已经在注册过程中了
        """
        try:
            # 只做初始化工作，不调用 server.register_role
            # 因为 server.register_role 已经在调用链中了
            return True
        except Exception:
            return False

    def _unregister(self, server: "MCPServer") -> bool:
        return server.unregister_role(self._llm.get_role_id())

    def wrap_mcp(self, data: Dict[str, Any]) -> MCPMessage:
        """
        将 LLM 响应包装为 MCP 协议

        data 格式：
        {
            "content": str,           # 文本响应
            "tool_calls": [...]       # 可选：工具调用列表
        }
        """
        source = MessageSource(
            role_id=self._llm.get_role_id(),
            role_type="llm",
            role_group=self._llm.get_role_group()
        )

        payload = MessagePayload(raw_content=data.get("content", ""))

        return MCPMessage(source=source, payload=payload)

    def unwrap_mcp(self, message: MCPMessage) -> Dict[str, Any]:
        """
        解析 MCP 协议，提取 LLM 所需信息

        返回：
        {
            "tools": [...],           # 来自 Tool 模块
            "resources": [...],       # 来自 Resource 模块
            "raw_content": str        # 用户原始输入
        }
        """
        result = {
            "raw_content": message.payload.raw_content or "",
            "tools": [],
            "resources": []
        }

        # 解析 tools
        for tool_def in message.payload.tools:
            result["tools"].append(tool_def.to_dict())

        # 解析 resources（直接注入到 messages）
        for resource in message.payload.resources:
            result["resources"].append(resource.to_dict())

        return result


class BaseLLM(BaseRole, ABC):
    """
    LLM 基类

    设计说明：
    1. 持有 LLMAdapter 实例
    2. 提供与 LLM 交互的抽象方法
    3. 子类实现具体的 LLM 调用逻辑
    """

    def __init__(self, adapter: LLMAdapter):
        super().__init__(adapter)
        self._client: Optional[Any] = None

    async def chat(
        self,
        messages: List[Dict[str, str]],
        tools: Optional[List[Dict[str, Any]]] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        与 LLM 对话

        Args:
            messages: 消息列表
            tools: 工具列表（来自 Tool/RAG 模块）

        Returns:
            LLM 响应
        """
        raise NotImplementedError("Subclasses must implement chat()")

    def get_role_type(self) -> str:
        return "llm"

    def get_role_group(self) -> Optional[str]:
        return "llm"

    def to_openai_format(self, tools: List[Any]) -> List[Dict[str, Any]]:
        """
        将 Tool 模块转换为 OpenAI tools 格式
        """
        return [tool.to_tool_def().to_dict() for tool in tools]

    def inject_resources_to_messages(
        self,
        messages: List[Dict[str, str]],
        resources: List[Resource]
    ) -> List[Dict[str, str]]:
        """
        将 Resource 注入到 messages 中
        """
        if not resources:
            return messages

        resource_content = "\n\n".join([
            f"[RESOURCE: {r.type}]\n{r.content}\n[/RESOURCE]"
            for r in resources
        ])

        injected_messages = []
        for msg in messages:
            injected_messages.append(msg.copy())
            if msg.get("role") == "user":
                injected_messages.append({
                    "role": "system",
                    "content": f"参考资源：\n{resource_content}"
                })

        return injected_messages
