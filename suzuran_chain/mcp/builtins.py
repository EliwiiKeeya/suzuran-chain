"""
MCP 内置角色

包含默认的用户角色和其他内置角色
"""
from typing import Optional, List, Dict, Any
from .protocol import Role, Adapter, MCPMessage


class DefaultUser(Role):
    """
    默认用户角色

    代表 Minecraft 游戏中的玩家
    """

    def __init__(self, role_id: str = "user:default-user"):
        adapter = DefaultUserAdapter(self)
        super().__init__(adapter)
        self._role_id = role_id

    def get_role_id(self) -> str:
        return self._role_id

    def get_role_type(self) -> str:
        return "user"

    def get_role_group(self) -> Optional[str]:
        return "players"

    def get_labels(self) -> List[str]:
        return ["minecraft", "player"]

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
        return context


class DefaultUserAdapter(Adapter):
    """
    默认用户适配器

    用户角色主要接收和发送消息，不需要特殊处理
    """

    def __init__(self, user: DefaultUser):
        self._user = user

    def _register(self, server: Any) -> bool:
        """注册用户角色（用户角色不需要特殊注册）"""
        return True

    def _unregister(self, server: Any) -> bool:
        """注销用户角色（用户角色不需要特殊注销）"""
        return True

    def wrap_mcp(self, data: Dict[str, Any]) -> "MCPMessage":
        """将用户输入包装为 MCP 消息"""
        from .protocol import MessageSource, MessagePayload

        source = MessageSource(
            role_id=self._user.get_role_id(),
            role_type=self._user.get_role_type(),
            role_group=self._user.get_role_group(),
            labels=self._user.get_labels()
        )

        payload = MessagePayload(raw_content=data.get("content", ""))

        from .protocol import MCPMessage
        return MCPMessage(source=source, payload=payload)

    def unwrap_mcp(self, message: "MCPMessage") -> Dict[str, Any]:
        """解析 MCP 消息，提取用户相关内容"""
        return {
            "raw_content": message.payload.raw_content or "",
            "role_id": message.source.role_id
        }
