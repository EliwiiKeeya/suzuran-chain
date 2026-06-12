"""
MCP 脚手架

提供最小可行的 MCP Server 架构
"""
import logging
from typing import Dict, List, Optional, Any, Callable
from .config import LLMConfig
from .server import MCPServer
from .protocol import Role, Adapter, MCPMessage, Prompt, MessageTarget
from ..llm.agent import Agent

logger = logging.getLogger(__name__)


class MCPScaffold:
    """
    MCP 脚手架

    提供最小可行的 MCP Server 架构，支持快速启动和动态扩展
    """

    def __init__(self, llm_config: LLMConfig):
        """
        初始化脚手架

        Args:
            llm_config: LLM 配置
        """
        self.llm_config = llm_config
        from .server import get_server
        self.server = get_server()  # 使用全局单例
        self._builtin_registry: Dict[str, Callable] = {}

        # 自动搭建最小工作环境
        self._setup_minimal_scaffold()

    def _setup_minimal_scaffold(self):
        """
        搭建最小工作环境

        注册：
        1. LLM 角色
        2. MCP 客户端接口角色
        3. 注册 LLM 和 RAG 消息处理器
        """
        logger.info("=" * 60)
        logger.info("搭建 MCP 脚手架...")
        logger.info("=" * 60)

        # 1. 注册 LLM
        llm = Agent()
        llm_role_id = self.server.register_role(llm)
        logger.info(f"✅ 注册 LLM: {llm_role_id}")

        # 2. 注册 MCP 客户端接口
        mcp_client = MCPClientInterface()
        client_role_id = self.server.register_role(mcp_client)
        logger.info(f"✅ 注册 MCP 客户端: {client_role_id}")

        # 3. 设置默认权限
        self.server.grant_permission(
            source_id=client_role_id,
            target_id=llm_role_id,
            permissions=["execute"],
            priority=100
        )
        self.server.grant_permission(
            source_id=llm_role_id,
            target_id=client_role_id,
            permissions=["execute"],
            priority=100
        )
        logger.info(f"✅ 配置默认权限")
        
        # 4. 注册消息处理器
        self.server.register_message_handler("llm", handle_llm_message)
        self.server.register_message_handler("agent", handle_llm_message)
        self.server.register_message_handler("rag", handle_rag_message)
        logger.info(f"✅ 注册 Agent 和 RAG 消息处理器")
        
        # 5. 注册 Prompt
        prompt = Prompt(
            system="""你是Suzuran，一个Minecraft游戏中的AI助手。
你可以理解玩家的指令并调用相应的功能来帮助他们。

当玩家给你发送消息时，分析他们的意图并决定如何响应。
如果需要调用功能，使用tool_calls。
否则直接回复玩家。"""
        )
        self.server.register_prompt("agent:default-prompt", prompt)
        logger.info(f"✅ 注册 Prompt")

        logger.info("=" * 60)
        logger.info("MCP 脚手架搭建完成")
        logger.info("=" * 60)

    def register_builtin(self, role: Role):
        """
        注册内置功能

        Args:
            role: 内置功能的 Role 实例
        """
        role_type = role.get_role_type()
        logger.info(f"注册内置功能: {role.get_role_id()} (type={role_type})")

        # 根据角色类型注册到服务器
        if role_type == "tool":
            role_id = self.server.register_tool(role)
        elif role_type == "rag":
            role_id = self.server.register_rag(role)
        else:
            role_id = self.server.register_role(role)

        # 记录到注册表
        self._builtin_registry[role_id] = role.__class__

        # 自动配置基础权限（允许 LLM 调用）
        self.server.grant_permission(
            source_id="agent:default-agent",
            target_id=role_id,
            permissions=["execute"],
            priority=100
        )

        return role_id

    def register_custom(self, role: Role) -> str:
        """
        注册自定义功能（含合规性检查）

        Args:
            role: 自定义功能的 Role 实例

        Returns:
            注册的角色 ID
        """
        logger.info(f"注册自定义功能: {role.role_id}")

        # 合规性检查
        self._validate_custom_role(role)

        # 注册到服务器
        role_id = self.server.register_role(role)

        return role_id

    def _validate_custom_role(self, role: Role):
        """
        验证自定义 Role 是否合规

        检查项：
        1. 必须是 Role 实例
        2. 必须有 Adapter
        3. role_id 不能冲突
        4. 必须有必要的方法
        """
        # 检查 1: 必须是 Role 实例
        if not isinstance(role, Role):
            raise TypeError(f"必须是 Role 实例，当前类型: {type(role)}")

        # 检查 2: 必须有 Adapter
        if not hasattr(role, '_adapter') or role._adapter is None:
            raise ValueError("Role 必须具有 Adapter")

        # 检查 3: role_id 不能冲突
        if role.role_id in self.server.role_manager.all_role_ids:
            raise ValueError(f"Role ID '{role.role_id}' 已存在")

        # 检查 4: 必须有必要的方法
        required_methods = ['get_role_id', 'get_role_type', 'can_send_message', 'can_receive_message']
        for method_name in required_methods:
            if not hasattr(role, method_name):
                raise ValueError(f"Role 必须实现方法: {method_name}")

        logger.debug(f"✅ 自定义 Role 验证通过: {role.role_id}")

    def unregister(self, role_id: str, force: bool = False) -> bool:
        """
        统一注销接口

        Args:
            role_id: 要注销的角色 ID
            force: 是否强制注销（忽略依赖）

        Returns:
            是否注销成功
        """
        logger.info(f"注销角色: {role_id}")

        # 检查是否存在
        if role_id not in self.server.role_manager.role_infos:
            raise ValueError(f"Role '{role_id}' 不存在")

        # 如果是内置功能，从注册表中移除
        if role_id in self._builtin_registry:
            del self._builtin_registry[role_id]

        # TODO: 实现依赖检查（如果 force=False）

        # 注销
        success = self.server.unregister_role(role_id)
        if success:
            logger.info(f"✅ 已注销: {role_id}")
        return success

    def unregister_by_label(self, label: str) -> List[str]:
        """
        基于标签注销

        Args:
            label: 标签

        Returns:
            已注销的角色 ID 列表
        """
        logger.info(f"基于标签注销: {label}")

        unregistered = []
        for role_id in list(self.server.role_manager.role_infos.keys()):
            role = self.server.get_role(role_id)
            if role and hasattr(role, 'get_labels') and label in role.get_labels():
                self.unregister(role_id, force=True)
                unregistered.append(role_id)

        logger.info(f"✅ 已注销 {len(unregistered)} 个角色: {unregistered}")
        return unregistered

    def get_registered_roles(self) -> List[str]:
        """获取所有已注册的角色 ID"""
        return list(self.server.role_manager.role_infos.keys())

    def get_builtin_roles(self) -> List[str]:
        """获取内置功能角色 ID"""
        return list(self._builtin_registry.keys())


class MCPClientInterface(Role):
    """
    MCP 客户端接口角色

    供 MC mod 等上游角色调用的接口
    """

    def __init__(self):
        adapter = MCPClientAdapter(self)
        super().__init__(adapter)
        self._role_id = "mcp:client"

    def get_role_id(self) -> str:
        return self._role_id

    def get_role_type(self) -> str:
        return "client"

    def get_role_group(self) -> Optional[str]:
        return "clients"

    def get_labels(self) -> List[str]:
        return ["mcp", "client", "interface"]

    def can_send_message(self) -> bool:
        return True

    def can_receive_message(self) -> bool:
        return True
    
    def handle(self, context: Any) -> Any:
        """
        处理 MCP 消息
        
        Args:
            context: unwrap_mcp() 解析得到的 MCP 上下文
        
        Returns:
            处理结果，将传给 wrap_mcp()
        """
        logger.info(f"MCPClientInterface handle: {context}")
        return context


class MCPClientAdapter(Adapter):
    """
    MCP 客户端适配器
    """

    def __init__(self, role: MCPClientInterface):
        self._role = role

    def _register(self, server: Any) -> bool:
        logger.info("MCPClientInterface 已注册")
        return True

    def _unregister(self, server: Any) -> bool:
        logger.info("MCPClientInterface 已注销")
        return True

    def wrap_mcp(self, data: Any) -> MCPMessage:
        """将数据打包成 MCP 协议格式（简单实现）"""
        return MCPMessage()

    def unwrap_mcp(self, message: MCPMessage) -> Any:
        """从 MCP 协议格式解包数据（简单实现）"""
        return message.payload.raw_content


async def handle_rag_message(message: MCPMessage) -> MCPMessage:
    """
    RAG 消息处理器
    """
    from .protocol import MessageSource, MessageTarget, MessagePayload, Resource

    logger = logging.getLogger(__name__)
    logger.info(f"[RAG Handler] 收到消息: {message.payload}")
    
    # 从消息中提取查询 - 优先使用 extra 中的 query（来自 tool_calls）
    query = message.payload.extra.get("query", message.payload.raw_content or "")
    logger.info(f"[RAG Handler] 使用查询: {query}")
    if not query:
        logger.error("[RAG Handler] 未找到查询内容")
        response = MCPMessage(
            source=MessageSource(
                role_id="rag:wiki",
                role_type="rag"
            ),
            target=message.source,
            payload=MessagePayload(raw_content="未找到查询内容")
        )
        return response
    
    # 获取 RAG 实例（使用全局 server 实例）
    from .server import get_server
    server = get_server()
    rag = server.rag_instances.get("rag:wiki")
    
    if not rag:
        logger.error("[RAG Handler] 未找到 RAG 实例")
        response = MCPMessage(
            source=MessageSource(
                role_id="rag:wiki",
                role_type="rag"
            ),
            target=message.source,
            payload=MessagePayload(raw_content="RAG 未注册")
        )
        return response
    
    # 执行检索
    content = await rag.retrieve(query)
    
    # 创建 Resource
    resource = rag.create_resource(
        server=server,
        content=content,
        metadata={"query": query}
    )
    
    logger.info(f"[RAG Handler] 创建 Resource: {resource.uri}")
    
    # 创建响应消息，携带 Resource
    response = MCPMessage(
        source=MessageSource(
            role_id="rag:wiki",
            role_type="rag"
        ),
        target=message.source,
        payload=MessagePayload(
            resources=[resource]
        )
    )
    
    # 立即释放 Resource（免鉴权）
    rag.release_resource(server, resource.uri)
    
    return response


async def handle_llm_message(message: MCPMessage) -> MCPMessage:
    """
    LLM 消息处理器

    设计说明：
    - 使用 Agent.handle() 处理消息
    - Agent 会自主判断是否调用 RAG Tool
    - 本处理器仅负责消息转发和响应
    """
    from .protocol import MessageSource, MessagePayload
    from suzuran_chain.llm.agent import get_agent

    user_content = message.payload.raw_content or ""
    logger = logging.getLogger(__name__)
    logger.info(f"[LLM Handler] 收到消息: {user_content}")
    
    if message.payload.tools:
        tool_call = message.payload.tools[0]
        logger.info(f"[LLM Handler] 收到工具调用: {tool_call.name}, params={tool_call.parameters}")

    if message.payload.resources:
        resource = message.payload.resources[0]
        logger.info(f"[LLM Handler] 收到 Resource: {resource.type}, content preview: {resource.content[:100]}...")

    # 使用单例 Agent
    agent = get_agent()
    result = agent.handle(message.payload)
    
    # 解析处理结果
    if isinstance(result, dict):
        if "response" in result:
            # 直接响应，不需要工具调用
            response_content = result["response"]
            logger.info(f"[LLM Handler] 发送最终响应: {response_content}")
            response = MCPMessage(
                source=MessageSource(
                    role_id="agent:default-agent",
                    role_type="agent"
                ),
                target=message.source,
                payload=MessagePayload(raw_content=response_content)
            )
        elif "needs_tool_call" in result:
            # 需要执行工具调用，构造工具调用消息并路由
            tool_calls = result.get("tool_calls", [])
            logger.info(f"[LLM Handler] 执行工具调用: {tool_calls}")
            
            # 构建工具调用消息
            tool_name = ""
            tool_args = {}
            for tc in tool_calls:
                tool_name = tc.get("name", "")
                args = tc.get("arguments", "{}")
                if isinstance(args, str):
                    import json
                    try:
                        tool_args = json.loads(args)
                    except:
                        tool_args = {}
            
            # 创建工具调用消息，目标为对应的工具/RAG
            tool_call_message = MCPMessage(
                source=MessageSource(
                    role_id="agent:default-agent",
                    role_type="agent"
                ),
                target=MessageTarget(
                    role_id=f"rag:{tool_name}" if tool_name else "unknown",
                    role_type="rag"
                ),
                payload=MessagePayload(
                    raw_content=user_content,
                    extra={"tool_calls": tool_calls, "query": tool_args.get("query", user_content)}
                )
            )
            
            # 递归调用 MCP Server 处理工具调用
            from .server import get_server
            server = get_server()
            rag_response = await server.process(tool_call_message)
            
            # 检查 RAG 响应是否是回调消息（包含 Resource）
            if rag_response.payload and rag_response.payload.resources:
                logger.info(f"[LLM Handler] 收到 RAG 回调，包含 {len(rag_response.payload.resources)} 个 Resource")
                
                # 现在需要再次调用 server.process() 处理回调，让 Agent 接收 Resource
                # 构造回调消息：source=rag, target=agent
                callback_message = MCPMessage(
                    source=rag_response.source or MessageSource(role_id="rag:wiki", role_type="rag"),
                    target=MessageTarget(role_id="agent:default-agent", role_type="agent"),
                    payload=rag_response.payload
                )
                
                # 递归处理回调，这会让 Agent._handle_tool_call() 接收 Resource
                final_response = await server.process(callback_message)
                return final_response
            
            # 没有 Resource，直接返回 RAG 响应（异常情况）
            return rag_response
        else:
            response_content = str(result)
            response = MCPMessage(
                source=MessageSource(
                    role_id="agent:default-agent",
                    role_type="agent"
                ),
                target=message.source,
                payload=MessagePayload(raw_content=response_content)
            )
    else:
        response_content = str(result)
        response = MCPMessage(
            source=MessageSource(
                role_id="agent:default-agent",
                role_type="agent"
            ),
            target=message.source,
            payload=MessagePayload(raw_content=response_content)
        )

    return response


async def call_llm_api(message: MCPMessage) -> str:
    """
    调用 LLM API（真实环境替换为实际 LLM 调用）

    Args:
        message: MCP 消息（包含用户输入、工具调用结果、Resource 等）

    Returns:
        LLM 响应内容
    """
    logger = logging.getLogger(__name__)
    user_content = message.payload.raw_content or ""

    if message.payload.resources:
        resource = message.payload.resources[0]
        query = resource.metadata.get("query", user_content) if resource.metadata else user_content
        logger.info(f"[LLM] 处理带 Resource 的查询: {query}")
        return f"关于 {query}，我找到了以下信息：\n\n{resource.content}"

    if message.payload.tools:
        tool_call = message.payload.tools[0]
        logger.info(f"[LLM] 处理工具调用结果: {tool_call.name}")
        return f"已执行工具 {tool_call.name}，结果已整合到上下文中。"

    logger.info(f"[LLM] 处理普通消息")
    return f"你好！我是铃兰，你的 Minecraft 助手。有什么我可以帮助你的吗？你可以说：{user_content}"
