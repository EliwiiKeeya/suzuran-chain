"""
MCP 路由模块（Bypass）

负责消息路由和分发，将消息传递给正确的处理程序

架构设计：
1. BaseRouter: 路由基类，定义统一接口
2. RouterManager: 路由管理器，维护路由表
3. 内建路由:
   - DefaultRouter: 处理未分配角色的默认请求
   - LLMRAGRouter: 处理LLM调用RAG的回调闭环
"""
from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, List, Optional
import logging
import asyncio

from .protocol import (
    MCPMessage,
    MessageTarget,
    MessagePayload,
    MessageSource,
    Resource
)
from .role import RoleManager, RoleInfo

logger = logging.getLogger(__name__)


class BaseRouter(ABC):
    """
    路由基类
    
    定义路由的统一接口，所有路由实现必须继承此类
    
    接口说明：
    - _register: 注册路由到路由表
    - _unregister: 从路由表注销路由
    - _route: 执行路由逻辑
    """
    
    def __init__(self, name: str = "base"):
        self.name = name
        self._is_registered = False
        
    @abstractmethod
    async def _route(self, message: MCPMessage) -> Optional[MCPMessage]:
        """
        执行路由逻辑
        
        Args:
            message: MCP 消息
            
        Returns:
            处理后的响应消息，如果此路由不处理该消息返回 None
        """
        pass
    
    @abstractmethod
    def _register(self, manager: 'RouterManager') -> None:
        """
        注册路由到管理器
        
        Args:
            manager: 路由管理器实例
        """
        pass
    
    @abstractmethod
    def _unregister(self, manager: 'RouterManager') -> bool:
        """
        从管理器注销路由
        
        Args:
            manager: 路由管理器实例
            
        Returns:
            是否成功注销
        """
        pass
    
    def can_handle(self, message: MCPMessage) -> bool:
        """
        判断此路由是否能处理该消息（可选覆盖）
        
        默认返回 True，子类可覆盖以实现精确匹配
        
        Args:
            message: MCP 消息
            
        Returns:
            是否能处理
        """
        return True


class DefaultRouter(BaseRouter):
    """
    App默认路由 - 适用于所有未分配角色的请求
    
    处理流程：
    1. 实例化临时默认角色并注册
    2. 默认分配Default LLM的访问权限
    3. 调用LLM
    4. 返回响应
    5. 释放临时默认角色
    """
    
    DEFAULT_ROLE_ID = "user:default"
    DEFAULT_ROLE_TYPE = "user"
    DEFAULT_ROLE_GROUP = "players"
    
    def __init__(self, default_llm_id: str = "agent:default-agent"):
        super().__init__(name="default")
        self.default_llm_id = default_llm_id
        self._temp_roles: Dict[str, Any] = {}
        
    async def _route(self, message: MCPMessage) -> Optional[MCPMessage]:
        """
        执行默认路由逻辑
        
        当消息没有明确目标或目标角色不存在时触发
        """
        logger.info(f"[DefaultRouter] Processing unassigned request from: {message.source.role_id if message.source else 'unknown'}")
        
        # 检查是否有默认LLM处理器
        handler = self._manager.get_handler("llm")
        if not handler:
            logger.warning("[DefaultRouter] No LLM handler available")
            return None
        
        try:
            # 设置目标为默认LLM
            if not message.target:
                message.target = MessageTarget(
                    role_id=self.default_llm_id,
                    role_type="llm"
                )
            
            logger.info(f"[DefaultRouter] Routing to default LLM: {self.default_llm_id}")
            response = await handler(message)
            
            return response
            
        except Exception as e:
            logger.error(f"[DefaultRouter] Error processing default route: {e}")
            return self._create_error_response(message, f"Default route error: {str(e)}")
    
    def _register(self, manager: 'RouterManager') -> None:
        """注册为默认路由"""
        self._manager = manager
        manager.set_default_router(self)
        self._is_registered = True
        logger.info("[DefaultRouter] Registered as default router")
        
    def _unregister(self, manager: 'RouterManager') -> bool:
        """注销默认路由"""
        if manager.get_default_router() == self:
            manager.set_default_router(None)
            self._is_registered = False
            logger.info("[DefaultRouter] Unregistered")
            return True
        return False
    
    def _create_error_response(self, message: MCPMessage, error: str) -> MCPMessage:
        return MCPMessage(
            source=MessageSource(role_id="mcp:router", role_type="system"),
            target=message.source if message.source else MessageSource(role_id="unknown", role_type="unknown"),
            payload=MessagePayload(raw_content=f"Error: {error}")
        )
    
    def can_handle(self, message: MCPMessage) -> bool:
        """
        判断是否应该使用默认路由
        
        条件：消息无目标 或 目标角色不存在
        """
        if not message.target:
            return True
        if not message.target.role_id:
            return True
        return False


class LLMRAGRouter(BaseRouter):
    """
    LLM调用RAG路由 - 处理LLM-RAG回调闭环
    
    处理流程：
    1. 当LLM的MCP协议包含RAG请求时，调用RAG，记录调用LLM的Src
    2. 调用RAG取得调用结果，注册为Resource对象，分配访问权限给调用的LLM
    3. 路由回调LLM，复用Src(避免鉴权)，本次回调将Resource加入History后释放Resource对象
    4. 路由结束，因为进入了下一轮LLM调用
    """
    
    RAG_CALL_PATTERN = "__rag_call__"
    
    def __init__(self):
        super().__init__(name="llm_rag")
        self._manager = None
        self._pending_rag_calls: Dict[str, Dict[str, Any]] = {}
        
    async def _route(self, message: MCPMessage) -> Optional[MCPMessage]:
        """
        执行LLM-RAG路由逻辑
        
        检测并处理两种情况：
        1. LLM发送RAG调用请求
        2. RAG返回结果需要回调LLM
        """
        target_type = message.target.role_type if message.target else None
        source_type = message.source.role_type if message.source else None
        
        # 情况1: LLM/Agent -> RAG (检测RAG调用)
        if source_type in ("llm", "agent") and target_type == "rag":
            return await self._handle_llm_to_rag(message)
        
        # 情况2: RAG -> LLM/Agent (RAG结果回调)
        elif source_type == "rag" and target_type in ("llm", "agent"):
            return await self._handle_rag_to_llm(message)
        
        return None
    
    async def _handle_llm_to_rag(self, message: MCPMessage) -> MCPMessage:
        """
        处理LLM到RAG的调用
        
        步骤：
        1. 记录调用源(LLM)
        2. 获取RAG处理器并调用
        3. 创建Resource并注册
        4. 回调LLM
        """
        llm_source = message.source
        rag_target = message.target
        
        logger.info(f"[LLMRAGRouter] LLM->RAG call: {llm_source.role_id} -> {rag_target.role_id}")
        
        # 记录本次RAG调用信息
        call_id = message.message_id
        self._pending_rag_calls[call_id] = {
            "source": llm_source,
            "target": rag_target,
            "timestamp": asyncio.get_event_loop().time()
        }
        
        # 获取RAG处理器
        rag_handler = self._manager.get_handler("rag")
        if not rag_handler:
            logger.error("[LLMRAGRouter] No RAG handler available")
            del self._pending_rag_calls[call_id]
            return MCPMessage(
                source=message.target,
                target=message.source,
                payload=MessagePayload(raw_content="Error: No RAG handler available")
            )
        
        try:
            # 调用RAG获取结果
            rag_response = await rag_handler(message)
            
            # 从RAG响应中提取Resource
            resources = []
            if rag_response.payload and rag_response.payload.resources:
                resources = rag_response.payload.resources
            
            logger.info(f"[LLMRAGRouter] RAG returned {len(resources)} resource(s)")
            
            # 创建回调消息给LLM（包含Resource）
            callback_message = MCPMessage(
                source=rag_response.source or MessageSource(
                    role_id=rag_target.role_id,
                    role_type="rag"
                ),
                target=llm_source,  # 回调给原调用者
                payload=MessagePayload(
                    raw_content=f"[RAG检索完成] 获取到 {len(resources)} 个资源",
                    resources=resources
                )
            )
            
            # 清理待处理调用记录
            if call_id in self._pending_rag_calls:
                del self._pending_rag_calls[call_id]
            
            return callback_message
            
        except Exception as e:
            logger.error(f"[LLMRAGRouter] Error in LLM->RAG: {e}")
            if call_id in self._pending_rag_calls:
                del self._pending_rag_calls[call_id]
            return MCPMessage(
                source=message.target,
                target=message.source,
                payload=MessagePayload(raw_content=f"Error: RAG call failed: {str(e)}")
            )
    
    async def _handle_rag_to_llm(self, message: MCPMessage) -> MCPMessage:
        """
        处理RAG到LLM的回调
        
        步骤：
        1. 验证回调合法性
        2. 将Resource加入History
        3. 触发下一轮LLM调用
        4. 释放Resource
        """
        logger.info(f"[LLMRAGRouter] RAG->LLM callback: {message.source.role_id} -> {message.target.role_id}")
        
        # 获取LLM处理器进行下一步处理
        llm_handler = self._manager.get_handler("llm")
        if not llm_handler:
            logger.warning("[LLMRAGRouter] No LLM handler for callback, returning RAG result directly")
            return message
        
        try:
            # 将RAG结果传递给LLM继续处理
            # 这里LLM会接收到包含Resource的消息，完成闭环
            llm_response = await llm_handler(message)
            
            # Resource已在LLM处理完成后释放（由server.py的_handle_rag_call负责）
            logger.info("[LLMRAGRouter] LLM-RAG cycle completed")
            
            return llm_response
            
        except Exception as e:
            logger.error(f"[LLMRAGRouter] Error in RAG->LLM callback: {e}")
            return MCPMessage(
                source=message.target,
                target=message.source,
                payload=MessagePayload(raw_content=f"Error: Callback failed: {str(e)}")
            )
    
    def _register(self, manager: 'RouterManager') -> None:
        """注册LLM-RAG路由"""
        self._manager = manager
        # 注册为特殊模式路由
        manager.register_pattern_router("llm:rag", self)
        manager.register_pattern_router("rag:llm", self)
        self._is_registered = True
        logger.info("[LLMRAGRouter] Registered for llm<->rag routing")
        
    def _unregister(self, manager: 'RouterManager') -> bool:
        """注销LLM-RAG路由"""
        manager.unregister_pattern_router("llm:rag")
        manager.unregister_pattern_router("rag:llm")
        self._is_registered = False
        self._manager = None
        logger.info("[LLMRAGRouter] Unregistered")
        return True
    
    def can_handle(self, message: MCPMessage) -> bool:
        """
        判断是否是LLM-RAG交互消息
        """
        if not message.source or not message.target:
            return False
        
        source_type = message.source.role_type
        target_type = message.target.role_type
        
        # LLM <-> RAG 的交互
        return (source_type in ("llm", "agent") and target_type == "rag") or \
               (source_type == "rag" and target_type in ("llm", "agent"))


class RouterManager:
    """
    路由管理器
    
    维护路由表，负责：
    - 路由匹配
    - 调用路由 route
    - 注册路由 register
    - 注销路由 unregister
    - 管理内建路由
    """
    
    def __init__(self, role_manager: RoleManager):
        """
        初始化路由管理器
        
        Args:
            role_manager: 角色管理器实例
        """
        self.role_manager = role_manager
        
        # 路由表
        self._pattern_routers: Dict[str, BaseRouter] = {}  # 按模式匹配的路由
        self._type_routers: Dict[str, BaseRouter] = {}     # 按角色类型匹配的路由
        self._custom_handlers: Dict[str, Callable] = {}     # 自定义处理器
        
        # 内建路由
        self._default_router: Optional[DefaultRouter] = None
        self._builtin_routers: List[BaseRouter] = []
        
        # 自动注册内建路由
        self._register_builtin_routers()
        
    def _register_builtin_routers(self) -> None:
        """
        注册所有内建路由
        
        内建路由包括：
        - DefaultRouter: 默认路由
        - LLMRAGRouter: LLM-RAG交互路由
        """
        # 注册默认路由
        default_router = DefaultRouter()
        default_router._register(self)
        self._builtin_routers.append(default_router)
        
        # 注册LLM-RAG路由
        llm_rag_router = LLMRAGRouter()
        llm_rag_router._register(self)
        self._builtin_routers.append(llm_rag_router)
        
        logger.info(f"[RouterManager] Registered {len(self._builtin_routers)} builtin routers")
    
    def register_handler(self, role_type: str, handler: Callable) -> None:
        """
        注册消息处理器（按角色类型）
        
        Args:
            role_type: 角色类型（如 "llm", "rag", "tool"）
            handler: 处理函数
        """
        self._custom_handlers[role_type] = handler
        logger.info(f"[RouterManager] Registered handler for type: {role_type}")
        
    def unregister_handler(self, role_type: str) -> bool:
        """
        注销消息处理器
        """
        if role_type in self._custom_handlers:
            del self._custom_handlers[role_type]
            return True
        return False
    
    def get_handler(self, role_type: str) -> Optional[Callable]:
        """
        获取指定类型的处理器
        """
        return self._custom_handlers.get(role_type)
    
    def register_pattern_router(self, pattern: str, router: BaseRouter) -> None:
        """
        注册按模式匹配的路由
        
        Args:
            pattern: 匹配模式（如 "llm:rag", "tool:*"）
            router: 路由实例
        """
        self._pattern_routers[pattern] = router
        logger.info(f"[RouterManager] Registered pattern router: {pattern} -> {router.name}")
        
    def unregister_pattern_router(self, pattern: str) -> bool:
        """
        注销按模式匹配的路由
        """
        if pattern in self._pattern_routers:
            del self._pattern_routers[pattern]
            return True
        return False
    
    def set_default_router(self, router: Optional[DefaultRouter]) -> None:
        """
        设置默认路由
        """
        self._default_router = router
        
    def get_default_router(self) -> Optional[DefaultRouter]:
        """
        获取默认路由
        """
        return self._default_router
    
    def match_route(self, message: MCPMessage) -> Optional[BaseRouter]:
        """
        匹配路由
        
        匹配优先级：
        1. 内建路由（LLMRAGRouter等）
        2. 模式路由
        3. 类型路由
        4. 默认路由
        """
        # 1. 检查内建路由是否能处理
        for router in self._builtin_routers:
            if router.can_handle(message):
                return router
        
        # 2. 检查模式路由
        if message.target and message.target.role_id:
            if message.target.role_id in self._pattern_routers:
                return self._pattern_routers[message.target.role_id]
        
        # 3. 检查类型路由
        if message.target and message.target.role_type:
            if message.target.role_type in self._type_routers:
                return self._type_routers[message.target.role_type]
        
        # 4. 返回默认路由
        return self._default_router
    
    async def route(self, message: MCPMessage) -> MCPMessage:
        """
        执行路由
        
        完整流程：
        1. 匹配合适的路由
        2. 调用路由的 _route 方法
        3. 如果没有匹配路由，尝试直接分发到处理器
        4. 返回响应
        """
        logger.info(f"[RouterManager] Routing message: {message.message_id}")
        
        # 匹配路由
        matched_router = self.match_route(message)
        
        if matched_router:
            logger.debug(f"[RouterManager] Matched router: {matched_router.name}")
            result = await matched_router._route(message)
            if result:
                return result
        
        # 如果没有路由处理，尝试直接按类型分发
        if message.target and message.target.role_type:
            handler = self.get_handler(message.target.role_type)
            if handler:
                logger.info(f"[RouterManager] Direct dispatch to: {message.target.role_type}")
                return await handler(message)
        
        # 使用默认路由
        if self._default_router:
            logger.info("[RouterManager] Using default router")
            return await self._default_router._route(message)
        
        # 无法路由
        logger.warning(f"[RouterManager] No route found for message: {message.message_id}")
        return self._create_error_response(message, "No route available")
    
    async def process(self, message: MCPMessage) -> MCPMessage:
        """
        完整处理消息（入口方法）
        """
        return await self.route(message)
    
    def list_routes(self) -> Dict[str, Any]:
        """
        列出所有已注册的路由
        """
        return {
            "builtin_routers": [r.name for r in self._builtin_routers],
            "pattern_routers": list(self._pattern_routers.keys()),
            "type_routers": list(self._type_routers.keys()),
            "handlers": list(self._custom_handlers.keys()),
            "has_default_router": self._default_router is not None
        }
    
    def reset(self) -> None:
        """
        重置路由管理器
        """
        self._pattern_routers.clear()
        self._type_routers.clear()
        self._custom_handlers.clear()
        self._builtin_routers.clear()
        self._default_router = None
        self._register_builtin_routers()
        logger.info("[RouterManager] Reset complete")
    
    def _create_error_response(self, message: MCPMessage, error: str) -> MCPMessage:
        """
        创建错误响应消息
        """
        return MCPMessage(
            source=MessageSource(
                role_id="mcp:router",
                role_type="system"
            ),
            target=message.source if message.source else MessageSource(role_id="unknown", role_type="unknown"),
            payload=MessagePayload(raw_content=f"Error: {error}")
        )


# 向后兼容的别名
MessageRouter = RouterManager
BypassRouter = RouterManager
