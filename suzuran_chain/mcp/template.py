"""
MCP 默认配置模板

定义 MVP 最小可行产品的角色和权限配置
"""

from typing import Dict, List, Any
from dataclasses import dataclass


@dataclass
class RoleConfig:
    """角色配置"""
    role_id: str
    role_type: str
    role_group: str
    labels: List[str]
    class_path: str
    init_params: Dict[str, Any]


@dataclass
class PermissionConfig:
    """权限配置"""
    source_id: str
    target_id: str
    permissions: List[str]
    priority: int


class MCPTemplate:
    """
    MCP 模板配置

    MVP 最小角色集合：
    1. User - 玩家角色
    2. LLM - AI 助手
    3. RAG - Wiki 知识检索
    """

    # MVP 默认角色配置
    DEFAULT_ROLES: List[RoleConfig] = [
        RoleConfig(
            role_id="user:default-user",
            role_type="user",
            role_group="players",
            labels=["minecraft", "player"],
            class_path="suzuran_chain.mcp.builtins:DefaultUser",
            init_params={}
        ),
        RoleConfig(
            role_id="agent:default-agent",
            role_type="agent",
            role_group="agent",
            labels=["ai", "assistant"],
            class_path="suzuran_chain.llm.agent:Agent",
            init_params={}
        ),
        RoleConfig(
            role_id="rag:wiki",
            role_type="rag",
            role_group="rag",
            labels=["wiki", "knowledge"],
            class_path="suzuran_chain.rag.wiki:WikiRAG",
            init_params={}
        ),
    ]

    # 默认权限配置
    DEFAULT_PERMISSIONS: List[PermissionConfig] = [
        PermissionConfig(
            source_id="user:default-user",
            target_id="agent:default-agent",
            permissions=["execute"],
            priority=100
        ),
        PermissionConfig(
            source_id="agent:default-agent",
            target_id="rag:wiki",
            permissions=["execute"],
            priority=100
        ),
        PermissionConfig(
            source_id="rag:wiki",
            target_id="agent:default-agent",
            permissions=["execute"],
            priority=100
        ),
    ]

    # 消息处理器配置
    MESSAGE_HANDLERS: Dict[str, str] = {
        "llm": "suzuran_chain.mcp.setup:handle_llm_message",
    }

    @classmethod
    def get_role_ids(cls) -> List[str]:
        """获取所有默认角色 ID"""
        return [role.role_id for role in cls.DEFAULT_ROLES]

    @classmethod
    def get_role_by_id(cls, role_id: str) -> RoleConfig:
        """根据 ID 获取角色配置"""
        for role in cls.DEFAULT_ROLES:
            if role.role_id == role_id:
                return role
        raise ValueError(f"Role not found: {role_id}")

    @classmethod
    def get_llm_role_id(cls) -> str:
        """获取默认 LLM 角色 ID"""
        return "agent:default-agent"

    @classmethod
    def get_user_role_id(cls) -> str:
        """获取默认用户角色 ID"""
        return "user:default-user"

    @classmethod
    def get_rag_roles(cls) -> List[RoleConfig]:
        """获取所有 RAG 角色配置"""
        return [role for role in cls.DEFAULT_ROLES if role.role_type == "rag"]


# 预定义常量
DEFAULT_USER_ROLE_ID = MCPTemplate.get_user_role_id()
DEFAULT_LLM_ROLE_ID = MCPTemplate.get_llm_role_id()
DEFAULT_RAG_ROLE_ID = "rag:wiki"
