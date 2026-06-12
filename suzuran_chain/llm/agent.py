from typing import List, Dict, Any, Optional
from enum import Enum
import logging

from ..llm.client import get_llm_client
from ..mcp.server import get_server, MCPServer
from ..mcp.role import Role, RoleData, Adapter
from ..mcp.protocol import MCPMessage, Prompt, MessagePayload

logger = logging.getLogger(__name__)


class AgentState(Enum):
    """Agent 状态枚举"""
    INITIAL = "initial"  # 初始化环节
    TOOL_CALL = "tool_call"  # 工具调用环节
    FINAL_RESPONSE = "final_response"  # 最终响应环节


class AgentAdapter(Adapter):

    def __init__(self, agent: "Agent"):
        self._agent = agent

    def _register(self, server: "MCPServer") -> bool:
        return True

    def _unregister(self, server: "MCPServer") -> bool:
        return True

    def wrap_mcp(self, data: Any) -> MCPMessage:
        return MCPMessage()

    def unwrap_mcp(self, message: MCPMessage) -> Any:
        return message.payload


class Agent(Role):
    def __init__(self):
        adapter = AgentAdapter(self)
        super().__init__(adapter)
        self.llm = get_llm_client()
        self._server: Optional[MCPServer] = None
        self._role_id = "agent:default-agent"
        self.conversation_history: List[Dict[str, str]] = []
        self.current_state = AgentState.INITIAL
        self.pending_tool_calls: List[Dict] = []
        self._last_user_message = ""
        self.MAX_TOOL_CALL_ROUNDS = 3
    
    def get_role_type(self) -> str:
        return "agent"

    def get_role_group(self) -> Optional[str]:
        return "agent"
    
    def get_labels(self) -> List[str]:
        return ["agent", "llm", "suzuran"]
    
    def get_metadata(self) -> Dict[str, Any]:
        return {
            "name": "Suzuran Agent",
            "description": "Minecraft AI 助手",
            "version": "1.0"
        }
    
    def get_role_id(self) -> str:
        return self._role_id

    def register(self, server: "MCPServer") -> bool:
        """注册到 MCP Server（委托给 Adapter）"""
        return self._adapter._register(server)

    def unregister(self, server: "MCPServer") -> bool:
        """从 MCP Server 注销（委托给 Adapter）"""
        return self._adapter._unregister(server)
    
    @property
    def server(self) -> MCPServer:
        """延迟获取服务器实例"""
        if self._server is None:
            self._server = get_server()
        return self._server
    
    def handle(self, context: Any) -> Any:
        """
        处理 MCP 消息
        
        Args:
            context: unwrap_mcp() 解析得到的 MessagePayload
        
        Returns:
            处理结果，将传给 wrap_mcp()
        """
        logger.info(f"Agent handle: state={self.current_state}, context={type(context)}")
        
        if isinstance(context, MessagePayload):
            # 如果 context 有 resources，说明是 RAG 回调
            if context.resources and len(context.resources) > 0:
                self.current_state = AgentState.TOOL_CALL
                return self._handle_tool_call(context)
        
        # 否则是正常的初始请求
        if self.current_state == AgentState.INITIAL:
            return self._handle_initial(context)
        elif self.current_state == AgentState.TOOL_CALL:
            return self._handle_tool_call(context)
        elif self.current_state == AgentState.FINAL_RESPONSE:
            return self._handle_final_response(context)
        else:
            logger.warning(f"Unknown state: {self.current_state}, fallback to INITIAL")
            self.current_state = AgentState.INITIAL
            return self._handle_initial(context)
    
    def _handle_initial(self, context: Any) -> Any:
        """
        处理初始化环节：从 MCP Server 获取动态 Prompt 和工具列表
        
        Args:
            context: MessagePayload 或用户消息
        
        Returns:
            处理结果
        """
        user_content = ""
        if isinstance(context, MessagePayload):
            user_content = context.raw_content or ""
        else:
            user_content = str(context)
            
        logger.info(f"Agent _handle_initial: {user_content}")
        
        # 从 MCP Server 获取 Prompt
        prompt = self.server.get_prompt("agent:default-prompt")
        if not prompt:
            logger.warning("Prompt not found, using fallback")
            prompt = Prompt(
                system="你是Suzuran，一个Minecraft游戏中的AI助手。"
            )
        
        # 从 MCP Server 获取可用工具
        available_tools = self.server.get_available_tools_for_role(self._role_id)
        
        # 动态构建系统提示词
        system_prompt = prompt.build_system_prompt(available_tools)
        
        # 构建 OpenAI 格式的消息
        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(self.conversation_history)
        messages.append({"role": "user", "content": user_content})
        
        # 构建工具定义
        tools = self._build_tools_from_available(available_tools)

        # 调用 LLM（使用 nest_asyncio 允许嵌套事件循环）
        import asyncio
        try:
            import nest_asyncio
            nest_asyncio.apply()
        except ImportError:
            pass

        response = asyncio.run(self.llm.chat(messages, tools=tools))
        
        if "tool_calls" in response:
            # 需要调用工具，切换状态
            self.current_state = AgentState.TOOL_CALL
            self.pending_tool_calls = response["tool_calls"]
            self._last_user_message = user_content
            logger.info(f"Need tool calls: {self.pending_tool_calls}")
            return {"needs_tool_call": True, "tool_calls": self.pending_tool_calls}
        else:
            # 直接返回响应
            self.current_state = AgentState.FINAL_RESPONSE
            assistant_message = response["content"]
            self.conversation_history.append({"role": "user", "content": user_content})
            self.conversation_history.append({"role": "assistant", "content": assistant_message})
            self._trim_conversation_history()
            logger.info(f"Direct response: {assistant_message}")
            return {"response": assistant_message}
    
    def _handle_tool_call(self, context: Any) -> Any:
        """
        处理工具调用环节：处理工具调用结果
        
        Args:
            context: MessagePayload 包含 Resource
        
        Returns:
            处理结果
        """
        logger.info(f"Agent _handle_tool_call: {context}")
        
        # 从 context 中获取 resources
        resources = []
        if isinstance(context, MessagePayload):
            resources = context.resources
        
        # 构建 tool response 消息
        tool_responses = []
        tool_call_id = self.pending_tool_calls[0]["id"] if self.pending_tool_calls else "unknown"
        for resource in resources:
            tool_responses.append({
                "role": "tool",
                "tool_call_id": tool_call_id,
                "content": resource.content
            })
        
        # 从 MCP Server 获取 Prompt
        prompt = self.server.get_prompt("agent:default-prompt")
        if not prompt:
            prompt = Prompt(system="你是Suzuran，一个Minecraft游戏中的AI助手。")
        
        available_tools = self.server.get_available_tools_for_role(self._role_id)
        system_prompt = prompt.build_system_prompt(available_tools)
        
        # 重建消息历史
        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(self.conversation_history)
        messages.append({"role": "user", "content": getattr(self, "_last_user_message", "")})
        
        # 添加 LLM 工具调用请求
        if self.pending_tool_calls:
            # 转换为 OpenAI 标准格式：tool_calls 包含 function 字段
            tool_calls_with_type = []
            for tc in self.pending_tool_calls:
                tool_calls_with_type.append({
                    "id": tc.get("id"),
                    "type": "function",
                    "function": {
                        "name": tc.get("name"),
                        "arguments": tc.get("arguments")
                    }
                })
            
            messages.append({
                "role": "assistant",
                "content": "",
                "tool_calls": tool_calls_with_type
            })
        
        # 添加工具响应
        messages.extend(tool_responses)
        
        logger.info(f"Agent calling LLM with tool responses: {len(tool_responses)} tool(s), messages: {messages}")
        
        # 再次调用 LLM
        import asyncio
        try:
            import nest_asyncio
            nest_asyncio.apply()
        except ImportError:
            pass

        response = asyncio.run(self.llm.chat(messages))
        
        # 生成最终响应
        self.current_state = AgentState.INITIAL
        self.pending_tool_calls = []
        assistant_message = response["content"]
        self.conversation_history.append({"role": "user", "content": getattr(self, "_last_user_message", "")})
        self.conversation_history.append({"role": "assistant", "content": assistant_message})
        self._trim_conversation_history()
        
        logger.info(f"Final response after tool call: {assistant_message}")
        return {"response": assistant_message}
    
    def _handle_final_response(self, context: Any) -> Any:
        """
        处理最终响应环节：构建最终回复
        
        Args:
            context: 最终上下文
        
        Returns:
            处理结果
        """
        logger.info(f"Agent _handle_final_response: {context}")
        self.current_state = AgentState.INITIAL
        return {"response": str(context)}
    
    def _build_tools_from_available(self, available_tools: List[Dict]) -> List[Dict]:
        """
        从可用工具列表构建 OpenAI 格式的工具定义
        
        Args:
            available_tools: 可用工具列表
        
        Returns:
            OpenAI 格式的工具定义
        """
        tools = []
        for tool in available_tools:
            tools.append({
                "type": "function",
                "function": {
                    "name": tool["name"],
                    "description": tool["description"],
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "要查询的关键词"
                            }
                        },
                        "required": ["query"]
                    }
                }
            })
        return tools
    
    def _trim_conversation_history(self) -> None:
        """裁剪对话历史，保持最近 20 条"""
        if len(self.conversation_history) > 20:
            self.conversation_history = self.conversation_history[-20:]


_agent = None


def get_agent() -> Agent:
    global _agent
    if _agent is None:
        _agent = Agent()
    return _agent
