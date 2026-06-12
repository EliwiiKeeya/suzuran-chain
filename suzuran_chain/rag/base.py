from typing import Dict, Any, Optional, List, TYPE_CHECKING
from abc import ABC
import uuid

# 导入协议层
from ..mcp.protocol import Role as BaseRole, Resource, MCPMessage, MessageSource, MessagePayload, Adapter

if TYPE_CHECKING:
    from ..mcp.server import MCPServer


class RAGAdapter(Adapter):
    """
    RAG 适配器

    功能：
    1. 解析 RAG 调用请求参数
    2. 执行检索逻辑
    3. 创建 Resource 实例并注册到 MCP Server
    4. 返回 Resource 信息给调用者
    """

    def __init__(self, rag: "BaseRAG"):
        self._rag = rag
        self._resource_registry: Dict[str, Resource] = {}

    def _register(self, server: "MCPServer") -> bool:
        """
        注册 RAG 到 MCP Server
        
        注意：此方法由 RoleManager 自动调用，不应该再次调用 server.register_role
        因为角色已经在注册过程中了
        """
        try:
            # 只做初始化工作，不调用 server.register_role
            # 因为 server.register_rag 已经会调用 server.register_role
            return True
        except Exception:
            return False

    def _unregister(self, server: "MCPServer") -> bool:
        # 注销时清理所有关联的 Resource
        for resource_id in list(self._resource_registry.keys()):
            self._release_resource(server, resource_id)
        return server.unregister_role(self._rag.get_role_id())

    def wrap_mcp(self, resource_instance: Resource) -> MCPMessage:
        """
        将检索结果 Resource 包装为 MCP 协议
        """
        source = MessageSource(
            role_id=self._rag.get_role_id(),
            role_type="rag",
            role_group=self._rag.get_role_group()
        )

        payload = MessagePayload(resources=[resource_instance])

        return MCPMessage(source=source, payload=payload)

    def unwrap_mcp(self, message: MCPMessage) -> Dict[str, Any]:
        """
        解析 RAG 调用请求
        """
        return {
            "query": message.payload.raw_content or "",
            "context": message.payload.prompt.context if message.payload.prompt else {}
        }

    def create_and_register_resource(
        self,
        server: "MCPServer",
        content: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Resource:
        """
        创建 Resource 实例并注册到 MCP Server
        """
        resource = Resource(
            type=self._rag.get_resource_type(),
            uri=f"rag://{self._rag.get_role_id()}/{uuid.uuid4()}",
            content=content,
            metadata=metadata or {}
        )

        resource_id = resource.uri
        self._resource_registry[resource_id] = resource

        return resource

    def release_resource(self, server: "MCPServer", resource_id: str) -> None:
        """
        释放 Resource 实例（从 MCP Server 注销）
        """
        if resource_id in self._resource_registry:
            del self._resource_registry[resource_id]

    def _release_resource(self, server: "MCPServer", resource_id: str) -> None:
        """内部方法，注销时调用"""
        self.release_resource(server, resource_id)


class BaseRAG(BaseRole, ABC):
    """
    RAG 基类

    设计说明：
    1. 持有 RAGAdapter 实例
    2. 提供检索的抽象方法
    3. 执行后创建 Resource 实例
    """

    def __init__(self, adapter: RAGAdapter):
        super().__init__(adapter)
        self._rag_adapter = adapter

    async def retrieve(self, query: str, **kwargs) -> str:
        """
        执行检索

        Args:
            query: 检索查询

        Returns:
            检索结果内容
        """
        raise NotImplementedError("Subclasses must implement retrieve()")

    def get_role_type(self) -> str:
        return "rag"

    def get_role_group(self) -> Optional[str]:
        return "rag"

    def get_resource_type(self) -> str:
        """
        获取资源类型（如 "wiki"）
        """
        raise NotImplementedError("Subclasses must implement get_resource_type()")

    def create_resource(
        self,
        server: "MCPServer",
        content: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Resource:
        """
        创建 Resource 实例并注册到 MCP Server
        """
        return self._rag_adapter.create_and_register_resource(
            server=server,
            content=content,
            metadata=metadata
        )

    def release_resource(self, server: "MCPServer", resource_id: str) -> None:
        """
        释放 Resource 实例
        """
        self._rag_adapter.release_resource(server, resource_id)
    
    def handle(self, context: Any) -> Any:
        """
        处理 MCP 消息
        
        Args:
            context: unwrap_mcp() 解析得到的 MCP 上下文
        
        Returns:
            处理结果，将传给 wrap_mcp()
        """
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"BaseRAG handle: {context}")
        return context
