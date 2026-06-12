from .protocol import (
    MCPMessage,
    Prompt,
    ToolDef,
    Resource,
    MessageSource,
    MessageTarget,
    MessageMetadata,
    MessagePayload,
)
from .role import Role, RoleData, BaseModel, Adapter, RoleInfo, RoleManager
from .permission import Permission, ACL, PermissionManager
from .server import MCPServer, get_server
from .audit import CallLog, AuditLogger, get_audit_logger
from .message_bus import MessageEnvelope, MessageBus, get_message_bus
from .bypass import MessageRouter, BypassRouter

# 延迟导入工具基类（已迁移到 tool 模块，避免循环依赖）
def __getattr__(name):
    if name in ("BaseTool", "SimpleTool"):
        from ..tool.base import BaseTool, SimpleTool
        return {"BaseTool": BaseTool, "SimpleTool": SimpleTool}[name]
    raise AttributeError(f"module 'suzuran_chain.mcp' has no attribute {name}")

__all__ = [
    "MCPMessage",
    "Prompt",
    "ToolDef",
    "BaseTool",
    "SimpleTool",
    "Resource",
    "MessageSource",
    "MessageTarget",
    "MessageMetadata",
    "MessagePayload",
    "Role",
    "RoleData",
    "BaseModel",
    "Adapter",
    "RoleInfo",
    "RoleManager",
    "Permission",
    "ACL",
    "PermissionManager",
    "MCPServer",
    "get_server",
    "CallLog",
    "AuditLogger",
    "get_audit_logger",
    "MessageEnvelope",
    "MessageBus",
    "get_message_bus",
    "MessageRouter",
    "BypassRouter"
]
