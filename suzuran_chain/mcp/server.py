from typing import Any, Callable, Dict, List, Optional, TYPE_CHECKING
import logging
import asyncio
from .protocol import (
    MCPMessage,
    Role,
    MessageTarget,
    MessagePayload,
    MessageSource,
    Prompt
)
from .role import RoleManager
from .permission import PermissionManager
from .bypass import RouterManager

if TYPE_CHECKING:
    from ..tool.base import BaseTool

logger = logging.getLogger(__name__)


class MCPServer:
    """
    MCP Server 核心类
    
    功能：
    1. 角色管理（通过 RoleManager）
    2. 权限管理（通过 PermissionManager）
    3. 工具注册与执行
    4. 消息处理与路由（通过 RouterManager）
    5. 适配器模式支持
    
    设计说明：
    - 职责分离：Adapter 负责协议封装，Role 负责业务逻辑
    - 强制类型检查：Role 必须持有 Adapter 实例
    - 路由逻辑委托给 RouterManager（bypass.py），包含内建路由：
      * DefaultRouter: 处理未分配角色的默认请求
      * LLMRAGRouter: 处理LLM调用RAG的回调闭环
    """
    
    def __init__(self):
        self.role_manager = RoleManager()
        self.permission_manager = PermissionManager()
        self.tool_instances: Dict[str, "BaseTool"] = {}
        self.rag_instances: Dict[str, Any] = {}  # RAG 实例
        self.prompt_instances: Dict[str, Prompt] = {}  # Prompt 实例
        
        # 使用新的路由管理器（包含内建路由）
        self.router = RouterManager(self.role_manager)
        
        self.permission_manager.create_default_acls()
        
        self._setup_default_roles()
    
    def _setup_default_roles(self) -> None:
        """
        设置默认角色（临时实现，后续通过 Role 实例注册）
        """
        # 创建默认的 LLM 角色占位符
        self._default_llm_role_id = "agent:default-agent"
        self._default_user_role_id = "user:default-user"

    def reset(self) -> None:
        """
        重置服务器状态

        清除所有已注册的角色、工具、RAG 实例和权限配置
        用于重新初始化或切换配置
        """
        self.role_manager = RoleManager()
        self.permission_manager = PermissionManager()
        self.tool_instances.clear()
        self.rag_instances.clear()
        self.router = RouterManager(self.role_manager)
        self.permission_manager.create_default_acls()
        self._setup_default_roles()
        logger.info("MCP Server 已重置")
    
    def register_role(self, role: Role) -> str:
        """
        注册角色实例
        
        Args:
            role: 角色实例（必须继承自 Role）
            
        Returns:
            角色 ID
        """
        role_id = self.role_manager.register_role(role, self)
        logger.info(f"Registered role: {role_id} (type={role.get_role_type()}, group={role.get_role_group()})")
        return role_id
    
    def unregister_role(self, role_id: str) -> bool:
        """
        注销角色
        
        Args:
            role_id: 角色 ID
            
        Returns:
            是否成功注销
        """
        result = self.role_manager.unregister_role(role_id, self)
        
        # 同时清理工具实例（如果是工具角色）
        if role_id in self.tool_instances:
            del self.tool_instances[role_id]
        
        if result:
            logger.info(f"Unregistered role: {role_id}")
        return result
    
    def get_role(self, role_id: str) -> Optional[Role]:
        """
        获取角色实例
        """
        return self.role_manager.get_role(role_id)
    
    def list_roles(self) -> Dict[str, Any]:
        """
        获取所有已注册角色
        
        Returns:
            角色字典
        """
        return self.role_manager.list_all_roles()
    
    def register_tool(self, tool: "BaseTool") -> str:
        """
        注册工具实例
        
        Args:
            tool: 工具实例（必须继承自 BaseTool）
            
        Returns:
            工具角色 ID
        """
        # 注册角色
        tool_id = self.register_role(tool)
        
        # 存储工具实例
        self.tool_instances[tool_id] = tool
        
        logger.info(f"Registered tool: {tool.name} (role_id={tool_id})")
        return tool_id
    
    def unregister_tool(self, tool_id: str) -> bool:
        """
        注销工具
        """
        if tool_id in self.tool_instances:
            del self.tool_instances[tool_id]
        
        return self.unregister_role(tool_id)
    
    def register_rag(self, rag: Any) -> str:
        """
        注册 RAG 实例
        
        Args:
            rag: RAG 实例（必须继承自 BaseRAG）
            
        Returns:
            RAG 角色 ID
        """
        # 注册角色
        rag_id = self.register_role(rag)
        
        # 存储 RAG 实例
        self.rag_instances[rag_id] = rag
        
        logger.info(f"Registered RAG: {rag.get_role_id()} (role_id={rag_id})")
        return rag_id
    
    def unregister_rag(self, rag_id: str) -> bool:
        """
        注销 RAG
        """
        if rag_id in self.rag_instances:
            del self.rag_instances[rag_id]
        
        return self.unregister_role(rag_id)
    
    def register_prompt(self, prompt_id: str, prompt: Prompt) -> bool:
        """
        注册 Prompt
        
        Args:
            prompt_id: Prompt ID
            prompt: Prompt 实例
        
        Returns:
            是否成功注册
        """
        self.prompt_instances[prompt_id] = prompt
        logger.info(f"Registered prompt: {prompt_id}")
        return True
    
    def get_prompt(self, prompt_id: str) -> Optional[Prompt]:
        """
        获取 Prompt
        
        Args:
            prompt_id: Prompt ID
        
        Returns:
            Prompt 实例，如果不存在返回 None
        """
        return self.prompt_instances.get(prompt_id)
    
    def update_prompt(self, prompt_id: str, prompt: Prompt) -> bool:
        """
        更新 Prompt
        
        Args:
            prompt_id: Prompt ID
            prompt: 新的 Prompt 实例
        
        Returns:
            是否成功更新
        """
        if prompt_id in self.prompt_instances:
            self.prompt_instances[prompt_id] = prompt
            logger.info(f"Updated prompt: {prompt_id}")
            return True
        logger.warning(f"Prompt not found for update: {prompt_id}")
        return False
    
    def unregister_prompt(self, prompt_id: str) -> bool:
        """
        注销 Prompt
        
        Args:
            prompt_id: Prompt ID
        
        Returns:
            是否成功注销
        """
        if prompt_id in self.prompt_instances:
            del self.prompt_instances[prompt_id]
            logger.info(f"Unregistered prompt: {prompt_id}")
            return True
        logger.warning(f"Prompt not found for unregister: {prompt_id}")
        return False
    
    def get_available_tools_for_role(self, role_id: str) -> List[Dict]:
        """
        获取角色可用的工具列表（时变）
        
        Args:
            role_id: 角色 ID
        
        Returns:
            可用工具列表，每个工具包含 name 和 description
        """
        available_tools = []
        
        # 添加 RAG 工具
        for rag_id, rag in self.rag_instances.items():
            if self.check_permission(role_id, rag_id, "execute"):
                tool_name = rag.name if hasattr(rag, "name") else "wiki_query"
                tool_description = rag.description if hasattr(rag, "description") else "检索 Minecraft Wiki"
                available_tools.append({
                    "name": tool_name,
                    "description": tool_description,
                    "id": rag_id
                })
        
        # 添加工具实例
        for tool_id, tool in self.tool_instances.items():
            if self.check_permission(role_id, tool_id, "execute"):
                available_tools.append({
                    "name": tool.name,
                    "description": tool.description,
                    "id": tool_id
                })
        
        return available_tools
    
    def register_message_handler(
        self,
        role_type: str,
        handler: Callable
    ) -> None:
        """
        注册消息处理器
        
        Args:
            role_type: 角色类型
            handler: 处理器函数
        """
        # 委托给路由管理器注册处理器
        self.router.register_handler(role_type, handler)
    
    def check_permission(
        self,
        source_id: str,
        target_id: str,
        action: str,
        context: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        检查权限
        """
        source_role = self.get_role(source_id)
        target_role = self.get_role(target_id)
        
        source_info = self.role_manager.get_role_info(source_id)
        target_info = self.role_manager.get_role_info(target_id)
        
        # 如果没有目标角色信息，直接拒绝
        if not target_info:
            logger.warning(f"Permission check failed: target role not found (target={target_id})")
            return False
        
        # 如果源角色信息不存在（比如外部客户端），尝试用默认信息
        if not source_info:
            logger.info(f"Source role not registered, using default info (source={source_id})")
            # 假设外部客户端属于 "clients" 组，类型为 "client"
            source_type = "client"
            source_group = "clients"
        else:
            source_type = source_info.role_type
            source_group = source_info.role_group
        
        return self.permission_manager.check_permission(
            source_id=source_id,
            source_type=source_type,
            source_group=source_group,
            target_id=target_id,
            target_type=target_info.role_type,
            target_group=target_info.role_group,
            action=action,
            context=context
        )
    
    def grant_permission(
        self,
        source_id: str,
        target_id: str,
        permissions: List[str],
        priority: int = 100
    ) -> str:
        """
        授予权限
        """
        acl_id = self.permission_manager.grant_permission(
            source_id=source_id,
            target_id=target_id,
            permissions=permissions,
            priority=priority
        )
        logger.info(f"Granted permissions: {source_id} -> {target_id}: {permissions}")
        return acl_id
    
    def list_permissions(self) -> Dict[str, Any]:
        """
        获取所有权限配置
        
        Returns:
            权限配置字典
        """
        return self.permission_manager.list_permissions()
    
    def list_routes(self) -> Dict[str, Any]:
        """
        获取所有已注册的路由信息
        
        Returns:
            路由配置字典，包含内建路由、模式路由、处理器等
        """
        return self.router.list_routes()
    
    def _create_default_target(self) -> MessageTarget:
        """
        创建默认目标（指向默认 LLM）
        """
        return MessageTarget(
            role_id=self._default_llm_role_id,
            role_type="llm"
        )
    
    def _create_error_response(self, message: MCPMessage, error: str) -> MCPMessage:
        """
        创建错误响应消息
        """
        return MCPMessage(
            source=MessageSource(
                role_id="mcp:server",
                role_type="system"
            ),
            target=message.source,
            payload=MessagePayload(raw_content=f"Error: {error}")
        )
    
    async def _send_and_forget(self, message: MCPMessage) -> None:
        """
        发送消息但不等待响应
        """
        try:
            await self.process(message)
        except Exception as e:
            logger.error(f"Failed to send message: {e}")
    
    async def process(self, message: MCPMessage) -> MCPMessage:
        """
        处理 MCP 消息（委托给路由管理器）
        
        职责：
        1. 权限检查
        2. 目标验证
        3. 路由委托（RouterManager 会自动选择合适的内建路由或自定义处理器）
        """
        logger.info(f"Processing message: {message.message_id}")
        
        # 详细记录来自 Agent 的消息
        if message.source and message.source.role_id and message.source.role_id.startswith("agent:"):
            logger.info(f"=== [Agent Message Received] ===")
            logger.info(f"Source: {message.source.role_id} (type={message.source.role_type})")
            logger.info(f"Target: {message.target.role_id if message.target else 'None'}")
            if message.payload:
                logger.info(f"Payload type: {type(message.payload).__name__}")
                if message.payload.raw_content:
                    logger.info(f"Raw content: {message.payload.raw_content[:200]}...")
                if message.payload.tools:
                    logger.info(f"Tool calls detected: {len(message.payload.tools)}")
                    for tool in message.payload.tools:
                        logger.info(f"  - Tool: {tool.name}, params: {tool.parameters}")
                if message.payload.resources:
                    logger.info(f"Resources attached: {len(message.payload.resources)}")
            logger.info(f"================================")
        
        if not message.source:
            logger.error("Message has no source")
            raise ValueError("Message must have a source")
        
        if not message.target:
            logger.info("No target specified, routing to default LLM")
            message.target = self._create_default_target()
        
        # 权限检查
        if not self.check_permission(
            source_id=message.source.role_id,
            target_id=message.target.role_id,
            action="execute"
        ):
            logger.warning(f"Permission denied: {message.source.role_id} -> {message.target.role_id}")
            return self._create_error_response(
                message=message,
                error="Permission denied"
            )
        
        # 目标角色验证
        target_role = self.get_role(message.target.role_id)
        if not target_role:
            logger.warning(f"Target role not found: {message.target.role_id}")
            return self._create_error_response(
                message=message,
                error="Target role not found"
            )
        
        # 委托给路由管理器进行路由和分发
        # RouterManager 会自动选择：
        # - LLMRAGRouter: 如果是LLM-RAG交互
        # - DefaultRouter: 如果是无目标的默认请求
        # - 自定义处理器: 其他情况
        return await self.router.process(message)


# 全局单例服务器实例
_server_instance: Optional[MCPServer] = None


def get_server() -> MCPServer:
    """
    获取全局 MCP Server 单例实例
    
    Returns:
        MCPServer 实例
    """
    global _server_instance
    if _server_instance is None:
        _server_instance = MCPServer()
    return _server_instance
