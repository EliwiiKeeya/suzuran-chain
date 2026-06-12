from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from datetime import datetime
import uuid
import json
from enum import Enum


class Permission(Enum):
    READ = "read"
    WRITE = "write"
    EXECUTE = "execute"
    ADMIN = "admin"


@dataclass
class ACL:
    # ============================================================
    # 冗余设计说明 (2026-05-26):
    # 权限系统预留了以下扩展点：
    #
    # 1. conditions: 条件约束字典，支持精细化权限控制
    #    - 未来可扩展: 时间条件、频率限制、IP 白名单等
    #    - 示例: {"max_calls_per_minute": 10, "allowed_ips": [...]}
    # 2. priority: ACL 优先级，支持覆盖和例外规则
    #    - 高优先级 ACL 可覆盖低优先级
    #    - 支持否定权限（如禁止某个特定角色）
    # 3. is_active: ACL 启用标志，支持临时禁用权限
    # 4. created_at/updated_at: 时间戳，支持权限审计
    #
    # 权限检查优先级（由高到低）:
    #    细粒度 ACL > 角色组权限 > 默认权限
    # ============================================================
    acl_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    source_role_id: str = ""
    target_role_id: str = ""
    permissions: List[str] = field(default_factory=list)
    priority: int = 0
    conditions: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    is_active: bool = True
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "acl_id": self.acl_id,
            "source_role_id": self.source_role_id,
            "target_role_id": self.target_role_id,
            "permissions": self.permissions,
            "priority": self.priority,
            "conditions": self.conditions,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "is_active": self.is_active
        }
    
    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ACL":
        return cls(
            acl_id=data.get("acl_id", str(uuid.uuid4())),
            source_role_id=data.get("source_role_id", ""),
            target_role_id=data.get("target_role_id", ""),
            permissions=data.get("permissions", []),
            priority=data.get("priority", 0),
            conditions=data.get("conditions", {}),
            created_at=data.get("created_at", datetime.utcnow().isoformat()),
            updated_at=data.get("updated_at", datetime.utcnow().isoformat()),
            is_active=data.get("is_active", True)
        )
    
    @classmethod
    def from_json(cls, json_str: str) -> "ACL":
        return cls.from_dict(json.loads(json_str))
    
    def has_permission(self, permission: str) -> bool:
        return permission in self.permissions
    
    def add_permission(self, permission: str) -> None:
        if permission not in self.permissions:
            self.permissions.append(permission)
            self.updated_at = datetime.utcnow().isoformat()
    
    def remove_permission(self, permission: str) -> None:
        if permission in self.permissions:
            self.permissions.remove(permission)
            self.updated_at = datetime.utcnow().isoformat()
    
    def check_condition(self, context: Dict[str, Any]) -> bool:
        if not self.conditions:
            return True
        
        for key, expected_value in self.conditions.items():
            actual_value = context.get(key)
            if actual_value != expected_value:
                return False
        
        return True


class PermissionManager:
    def __init__(self):
        self.acls: Dict[str, ACL] = {}
        self.role_acls: Dict[str, List[str]] = {}
        self.group_permissions: Dict[str, Dict[str, List[str]]] = {}
        self.default_permissions: Dict[str, List[str]] = {
            "read": ["user", "llm", "tool", "system", "client"],
            "write": ["user", "llm", "system", "client"],
            "execute": ["user", "llm", "client"],
            "admin": ["system"]
        }
    
    def set_acl(self, acl: ACL) -> str:
        if not acl.acl_id:
            acl.acl_id = str(uuid.uuid4())
        
        self.acls[acl.acl_id] = acl
        
        key = f"{acl.source_role_id}:{acl.target_role_id}"
        if key not in self.role_acls:
            self.role_acls[key] = []
        if acl.acl_id not in self.role_acls[key]:
            self.role_acls[key].append(acl.acl_id)
        
        return acl.acl_id
    
    def remove_acl(self, acl_id: str) -> bool:
        if acl_id not in self.acls:
            return False
        
        acl = self.acls[acl_id]
        key = f"{acl.source_role_id}:{acl.target_role_id}"
        if key in self.role_acls and acl_id in self.role_acls[key]:
            self.role_acls[key].remove(acl_id)
        
        del self.acls[acl_id]
        return True
    
    def get_acl(self, source_id: str, target_id: str) -> Optional[ACL]:
        key = f"{source_id}:{target_id}"
        acl_ids = self.role_acls.get(key, [])
        
        if not acl_ids:
            return None
        
        active_acls = [
            self.acls[aid] for aid in acl_ids 
            if aid in self.acls and self.acls[aid].is_active
        ]
        
        if not active_acls:
            return None
        
        return max(active_acls, key=lambda a: a.priority)
    
    def set_group_permission(
        self,
        source_group: str,
        target_group: str,
        permissions: List[str]
    ) -> None:
        if source_group not in self.group_permissions:
            self.group_permissions[source_group] = {}
        self.group_permissions[source_group][target_group] = permissions
    
    def get_group_permission(
        self,
        source_group: str,
        target_group: str
    ) -> Optional[List[str]]:
        return self.group_permissions.get(source_group, {}).get(target_group)
    
    def set_default_permission(self, action: str, role_types: List[str]) -> None:
        self.default_permissions[action] = role_types
    
    def get_default_permission(self, action: str) -> List[str]:
        return self.default_permissions.get(action, [])
    
    def check_permission(
        self,
        source_id: str,
        source_type: str,
        source_group: Optional[str],
        target_id: str,
        target_type: str,
        target_group: Optional[str],
        action: str,
        context: Optional[Dict[str, Any]] = None
    ) -> bool:
        acl = self.get_acl(source_id, target_id)
        if acl and acl.is_active:
            if acl.check_condition(context or {}):
                if acl.has_permission(action):
                    return True
        
        if source_group and target_group:
            group_perms = self.get_group_permission(source_group, target_group)
            if group_perms and action in group_perms:
                return True
        
        default_types = self.get_default_permission(action)
        if source_type in default_types:
            return True
        
        return False
    
    def list_acls(self) -> Dict[str, Dict[str, Any]]:
        return {aid: acl.to_dict() for aid, acl in self.acls.items()}
    
    def list_group_permissions(self) -> Dict[str, Dict[str, List[str]]]:
        return self.group_permissions.copy()
    
    def list_permissions(self) -> Dict[str, Any]:
        """
        获取所有权限配置
        
        Returns:
            权限配置字典，包含 ACLs、角色组权限和默认权限
        """
        return {
            "acls": self.list_acls(),
            "group_permissions": self.list_group_permissions(),
            "default_permissions": self.default_permissions.copy()
        }
    
    def create_default_acls(self) -> None:
        self.set_group_permission("players", "models", ["execute"])
        self.set_group_permission("models", "tools", ["execute"])
        self.set_group_permission("systems", "models", ["read", "write", "execute"])
        self.set_group_permission("systems", "tools", ["read", "write", "execute"])
    
    def grant_permission(
        self,
        source_id: str,
        target_id: str,
        permissions: List[str],
        priority: int = 100,
        conditions: Optional[Dict[str, Any]] = None
    ) -> str:
        acl = ACL(
            source_role_id=source_id,
            target_role_id=target_id,
            permissions=permissions,
            priority=priority,
            conditions=conditions or {}
        )
        return self.set_acl(acl)
    
    def revoke_permission(
        self,
        source_id: str,
        target_id: str,
        permission: Optional[str] = None
    ) -> bool:
        acl = self.get_acl(source_id, target_id)
        if not acl:
            return False
        
        if permission:
            acl.remove_permission(permission)
            return True
        else:
            return self.remove_acl(acl.acl_id)
