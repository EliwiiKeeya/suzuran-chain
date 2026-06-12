from typing import Dict, Any, Optional, List, Callable, TYPE_CHECKING
from abc import ABC, abstractmethod

# 导入角色基类和适配器基类
from ..mcp.role import Role, Adapter

if TYPE_CHECKING:
    from ..mcp.server import MCPServer
    from ..mcp.protocol import ToolDef, MCPMessage, MessageSource, MessagePayload


class ToolAdapter(Adapter):
    """
    工具适配器

    功能：
    1. 实现工具的注册/注销
    2. 实现工具调用结果的 MCP 协议封装
    3. 实现工具调用请求的 MCP 协议解封装
    """

    def __init__(self, tool: "BaseTool"):
        self._tool = tool

    def _register(self, server: "MCPServer") -> bool:
        """
        注册工具到 MCP Server
        
        注意：此方法由 RoleManager 自动调用，不应该再次调用 server.register_tool
        因为工具已经在注册过程中了
        """
        try:
            # 只做初始化工作，不调用 server.register_tool
            # 因为 server.register_tool 已经会调用 server.register_role
            return True
        except Exception:
            return False

    def _unregister(self, server: "MCPServer") -> bool:
        try:
            return server.unregister_tool(self._tool.get_role_id())
        except Exception:
            return False

    def wrap_mcp(self, result: Any) -> "MCPMessage":
        """
        包装工具执行结果为 MCP 协议格式
        """
        # 延迟导入避免循环依赖
        from ..mcp.protocol import MessagePayload, MessageSource, MCPMessage
        
        payload = MessagePayload(
            raw_content=str(result) if result is not None else ""
        )

        source = MessageSource(
            role_id=self._tool.get_role_id(),
            role_type="tool",
            role_group=self._tool.get_role_group(),
            labels=self._tool.get_labels()
        )

        return MCPMessage(
            source=source,
            payload=payload
        )

    def unwrap_mcp(self, message: "MCPMessage") -> Dict[str, Any]:
        """
        解析工具调用请求
        """
        if not message.payload.tools:
            return {}

        tool = message.payload.tools[0]
        return tool.parameters


class BaseTool(Role, ABC):
    """
    工具基类
    
    使用说明：
    1. 继承此类并实现 execute() 方法
    2. 自动持有 ToolAdapter 实例
    3. MCP Server 可以通过 Role 接口无缝管理
    """
    
    def __init__(self, name: str, description: str = ""):
        """
        初始化工具
        
        Args:
            name: 工具名称
            description: 工具描述
        """
        # 创建适配器实例（不再有循环依赖）
        adapter = ToolAdapter(self)
        
        # 调用父类初始化（强制类型检查）
        super().__init__(adapter)
        
        self.name = name
        self.description = description
    
    @abstractmethod
    async def execute(self, params: Dict[str, Any]) -> Any:
        """
        执行工具（子类必须实现）
        
        Args:
            params: 工具参数
            
        Returns:
            执行结果
        """
        pass
    
    def get_role_id(self) -> str:
        """获取工具 ID"""
        return self.role_id or f"tool:{self.name}"
    
    def get_role_type(self) -> str:
        """获取角色类型"""
        return "tool"
    
    def get_role_group(self) -> Optional[str]:
        """获取角色组"""
        return "tools"
    
    def get_labels(self) -> List[str]:
        """获取标签"""
        return [self.name, "tool"]
    
    def get_metadata(self) -> Dict[str, Any]:
        """获取元数据"""
        return {
            "name": self.name,
            "description": self.description
        }
    
    def to_tool_def(self) -> "ToolDef":
        """转换为 MCP 协议中的工具定义格式"""
        # 延迟导入避免循环依赖
        from ..mcp.protocol import ToolDef
        
        return ToolDef(
            name=self.name,
            description=self.description,
            parameters=self.get_parameters_schema()
        )
    
    def get_parameters_schema(self) -> Dict[str, Any]:
        """
        获取参数 Schema（子类可重写）
        
        默认返回空字典
        """
        return {}
    
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
        logger.info(f"BaseTool handle: {context}")
        return context


class SimpleTool(BaseTool):
    """
    简单工具模板
    
    使用说明：
    1. 适合简单的同步工具
    2. 直接传入执行函数即可
    """
    
    def __init__(self, name: str, description: str, func: Callable):
        """
        初始化简单工具
        
        Args:
            name: 工具名称
            description: 工具描述
            func: 执行函数（可以是同步或异步）
        """
        super().__init__(name, description)
        self._func = func
    
    async def execute(self, params: Dict[str, Any]) -> Any:
        """
        执行工具
        """
        import inspect
        
        if inspect.iscoroutinefunction(self._func):
            return await self._func(**params)
        else:
            return self._func(**params)


__all__ = [
    "ToolAdapter",
    "BaseTool",
    "SimpleTool"
]
