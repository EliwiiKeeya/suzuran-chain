from typing import Dict, Any, Optional, List, TYPE_CHECKING
from abc import ABC

# 导入协议层
from ..mcp.protocol import Role as BaseRole, MCPMessage, MessageSource, MessagePayload, Adapter

if TYPE_CHECKING:
    from ..mcp.server import MCPServer


class ResourceAdapter(Adapter):
    """
    Resource 适配器

    功能：
    1. 将 Resource 内容包装为 MCP 协议
    2. 后处理：在内容前添加提示词，区分注入格式
    """

    def __init__(self, resource: "BaseResource"):
        self._resource = resource

    def _register(self, server: "MCPServer") -> bool:
        try:
            resource_id = server.register_role(self._resource)
            return resource_id is not None
        except Exception:
            return False

    def _unregister(self, server: "MCPServer") -> bool:
        return server.unregister_role(self._resource.get_role_id())

    def wrap_mcp(self, processed_content: str) -> MCPMessage:
        """
        将处理后的 Resource 内容包装为 MCP 协议
        """
        source = MessageSource(
            role_id=self._resource.get_role_id(),
            role_type="resource",
            role_group=self._resource.get_role_group(),
            labels=self._resource.get_labels()
        )

        payload = MessagePayload(raw_content=processed_content)

        return MCPMessage(source=source, payload=payload)

    def unwrap_mcp(self, message: MCPMessage) -> Dict[str, Any]:
        """
        解析 Resource 请求（通常 Resource 不会主动被调用）
        """
        return {}

    def post_process(self, content: str) -> str:
        """
        后处理：在内容前添加提示词

        格式：
        [RESOURCE START: {resource_type}]
        {content}
        [RESOURCE END]
        """
        resource_type = self._resource.get_resource_type()
        return (
            f"[RESOURCE START: {resource_type}]\n"
            f"{content}\n"
            f"[RESOURCE END]"
        )


class BaseResource(BaseRole, ABC):
    """
    Resource 基类

    设计说明：
    1. 持有 ResourceAdapter 实例
    2. 主要提供内容，不主动调用其他角色
    3. 后处理：在内容前连接提示词
    """

    def __init__(self, adapter: ResourceAdapter):
        super().__init__(adapter)
        self._resource_adapter = adapter
        self._content: str = ""

    def get_content(self) -> str:
        """
        获取资源内容
        """
        raise NotImplementedError("Subclasses must implement get_content()")

    def get_resource_type(self) -> str:
        """
        获取资源类型
        """
        raise NotImplementedError("Subclasses must implement get_resource_type()")

    def get_role_type(self) -> str:
        return "resource"

    def get_role_group(self) -> Optional[str]:
        return "resource"

    def get_labels(self) -> List[str]:
        return [self.get_resource_type(), "resource"]

    def get_metadata(self) -> Dict[str, Any]:
        return {
            "resource_type": self.get_resource_type(),
            "content_length": len(self.get_content())
        }

    def post_process(self) -> str:
        """
        后处理：添加提示词包装

        输出格式：
        [RESOURCE START: {resource_type}]
        {content}
        [RESOURCE END]
        """
        return self._resource_adapter.post_process(self.get_content())
