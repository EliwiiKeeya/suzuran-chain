from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Callable, TYPE_CHECKING
from datetime import datetime
from abc import ABC, abstractmethod
import uuid
import json

# 从 role.py 导入已迁移的类
from .role import Adapter, Role, RoleData, BaseModel

if TYPE_CHECKING:
    from .server import MCPServer


# ============================================================
# MCP 协议核心组件（运行时数据流）
# ============================================================

@dataclass
class Prompt:
    system: str = ""
    context: Dict[str, Any] = field(default_factory=dict)
    instructions: List[str] = field(default_factory=list)
    
    def build_system_prompt(self, tools: List[Dict]) -> str:
        """
        根据可用工具动态构建系统提示词
        
        Args:
            tools: 可用工具列表，每个工具包含 name 和 description
        
        Returns:
            完整的系统提示词
        """
        if not tools:
            return self.system
        
        tool_list = "\n".join([f"- {t['name']}: {t['description']}" for t in tools])
        return f"{self.system}\n\n可用的功能：\n{tool_list}"
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "system": self.system,
            "context": self.context,
            "instructions": self.instructions
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Prompt":
        return cls(
            system=data.get("system", ""),
            context=data.get("context", {}),
            instructions=data.get("instructions", [])
        )


@dataclass
class ToolDef:
    """工具定义（MCP协议中的tool结构）"""
    name: str
    description: str
    parameters: Dict[str, Any] = field(default_factory=dict)
    handler: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
            "handler": self.handler
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ToolDef":
        return cls(
            name=data["name"],
            description=data.get("description", ""),
            parameters=data.get("parameters", {}),
            handler=data.get("handler")
        )


@dataclass
class Resource:
    type: str
    uri: str
    content: Any = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.type,
            "uri": self.uri,
            "content": self.content,
            "metadata": self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Resource":
        return cls(
            type=data["type"],
            uri=data["uri"],
            content=data.get("content"),
            metadata=data.get("metadata", {})
        )


@dataclass
class MessageSource:
    role_id: str
    role_type: str
    role_group: Optional[str] = None
    labels: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "role_id": self.role_id,
            "role_type": self.role_type,
            "role_group": self.role_group,
            "labels": self.labels
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MessageSource":
        return cls(
            role_id=data["role_id"],
            role_type=data["role_type"],
            role_group=data.get("role_group"),
            labels=data.get("labels", [])
        )


@dataclass
class MessageTarget:
    role_id: str
    role_type: str
    role_group: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "role_id": self.role_id,
            "role_type": self.role_type,
            "role_group": self.role_group
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MessageTarget":
        return cls(
            role_id=data["role_id"],
            role_type=data["role_type"],
            role_group=data.get("role_group")
        )


@dataclass
class MessageMetadata:
    priority: int = 0
    ttl: int = 3600
    requires_response: bool = True
    audit_level: str = "low"
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "priority": self.priority,
            "ttl": self.ttl,
            "requires_response": self.requires_response,
            "audit_level": self.audit_level
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MessageMetadata":
        return cls(
            priority=data.get("priority", 0),
            ttl=data.get("ttl", 3600),
            requires_response=data.get("requires_response", True),
            audit_level=data.get("audit_level", "low")
        )


@dataclass
class MessagePayload:
    prompt: Optional[Prompt] = None
    tools: List[ToolDef] = field(default_factory=list)
    resources: List[Resource] = field(default_factory=list)
    raw_content: Optional[str] = None
    extra: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "prompt": self.prompt.to_dict() if self.prompt else None,
            "tools": [tool.to_dict() for tool in self.tools],
            "resources": [resource.to_dict() for resource in self.resources],
            "raw_content": self.raw_content,
            "extra": self.extra
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MessagePayload":
        prompt_data = data.get("prompt")
        return cls(
            prompt=Prompt.from_dict(prompt_data) if prompt_data else None,
            tools=[ToolDef.from_dict(t) for t in data.get("tools", [])],
            resources=[Resource.from_dict(r) for r in data.get("resources", [])],
            raw_content=data.get("raw_content"),
            extra=data.get("extra", {})
        )


@dataclass
class MCPMessage:
    """
    MCP 消息格式
    
    设计说明：
    1. 统一消息格式，支持同步/异步通信
    2. 兼容 MCP 协议规范
    3. 支持工具调用和资源传递
    """
    source: MessageSource
    target: Optional[MessageTarget] = None
    payload: MessagePayload = field(default_factory=MessagePayload)
    metadata: MessageMetadata = field(default_factory=MessageMetadata)
    message_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    reply_to: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "message_id": self.message_id,
            "source": self.source.to_dict(),
            "target": self.target.to_dict() if self.target else None,
            "payload": self.payload.to_dict(),
            "metadata": self.metadata.to_dict(),
            "reply_to": self.reply_to
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MCPMessage":
        source_data = data.get("source", {})
        target_data = data.get("target")
        return cls(
            message_id=data.get("message_id", str(uuid.uuid4())),
            source=MessageSource.from_dict(source_data),
            target=MessageTarget.from_dict(target_data) if target_data else None,
            payload=MessagePayload.from_dict(data.get("payload", {})),
            metadata=MessageMetadata.from_dict(data.get("metadata", {})),
            reply_to=data.get("reply_to")
        )
    
    @classmethod
    def create_user_message(
        cls,
        user_id: str,
        content: str,
        user_group: Optional[str] = None,
        target_id: Optional[str] = None,
        target_type: Optional[str] = None
    ) -> "MCPMessage":
        """
        创建用户消息
        """
        source = MessageSource(
            role_id=user_id,
            role_type="user",
            role_group=user_group
        )
        
        target = None
        if target_id and target_type:
            target = MessageTarget(
                role_id=target_id,
                role_type=target_type
            )
        
        payload = MessagePayload(raw_content=content)
        
        return cls(source=source, target=target, payload=payload)
    
    @classmethod
    def create_tool_call(cls, tool: ToolDef, source_role_id: str, source_role_type: str) -> "MCPMessage":
        """
        创建工具调用消息
        """
        source = MessageSource(
            role_id=source_role_id,
            role_type=source_role_type
        )
        
        target = MessageTarget(
            role_id=f"tool:{tool.name}",
            role_type="tool"
        )
        
        payload = MessagePayload(tools=[tool])
        
        return cls(source=source, target=target, payload=payload)


# ============================================================
# BaseTool / SimpleTool - 已迁移到 tool 模块
# 为了避免循环依赖，这里不直接导入
# 请使用: from suzuran_chain.tool import BaseTool, SimpleTool
# 或: from suzuran_chain.mcp import BaseTool, SimpleTool (通过 __init__.py)
# ============================================================
