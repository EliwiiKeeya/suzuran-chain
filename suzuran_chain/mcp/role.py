from typing import Any, Callable, Dict, List, Optional, TYPE_CHECKING
from datetime import datetime
from dataclasses import dataclass, field
from abc import ABC, abstractmethod
import uuid

if TYPE_CHECKING:
    from .server import MCPServer


# ============================================================
# 注册数据模型（与 MCP 协议独立）
# ============================================================

@dataclass
class BaseModel:
    """注册数据基类，用于角色注册/注销的数据格式"""
    role_type: str
    role_group: Optional[str] = None
    labels: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    is_active: bool = True
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "role_type": self.role_type,
            "role_group": self.role_group,
            "labels": self.labels,
            "metadata": self.metadata,
            "is_active": self.is_active
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "BaseModel":
        return cls(
            role_type=data["role_type"],
            role_group=data.get("role_group"),
            labels=data.get("labels", []),
            metadata=data.get("metadata", {}),
            is_active=data.get("is_active", True)
        )


@dataclass
class RoleData(BaseModel):
    """角色注册数据模型"""
    role_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    
    def to_dict(self) -> Dict[str, Any]:
        result = super().to_dict()
        result.update({
            "role_id": self.role_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at
        })
        return result
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RoleData":
        return cls(
            role_id=data.get("role_id", str(uuid.uuid4())),
            role_type=data["role_type"],
            role_group=data.get("role_group"),
            labels=data.get("labels", []),
            metadata=data.get("metadata", {}),
            is_active=data.get("is_active", True),
            created_at=data.get("created_at", datetime.utcnow().isoformat()),
            updated_at=data.get("updated_at", datetime.utcnow().isoformat())
        )


# ============================================================
# Adapter 基类（协议层）
# ============================================================

class Adapter(ABC):
    """协议适配器基类，负责 MCP 协议的封装/解封装、注册/注销"""

    def _register(self, server: "MCPServer") -> bool:
        """
        注册到 MCP Server

        注意：此方法由 RoleManager 自动调用，子类必须实现
        """
        raise NotImplementedError("Subclasses must implement _register()")

    def _unregister(self, server: "MCPServer") -> bool:
        """
        从 MCP Server 注销

        注意：此方法由 RoleManager 自动调用，子类必须实现
        """
        raise NotImplementedError("Subclasses must implement _unregister()")

    def wrap_mcp(self, data: any) -> "MCPMessage":
        """
        将数据打包成 MCP 协议格式

        默认实现抛出 NotImplementedError，子类应根据需要重写
        """
        raise NotImplementedError("Subclasses must implement wrap_mcp()")

    def unwrap_mcp(self, message: "MCPMessage") -> any:
        """
        从 MCP 协议格式解包数据

        默认实现抛出 NotImplementedError，子类应根据需要重写
        """
        raise NotImplementedError("Subclasses must implement unwrap_mcp()")


# ============================================================
# Role 基类（业务层）
# ============================================================

class Role(ABC):
    """
    角色基类
    
    设计说明：
    1. 强制持有 Adapter 实例，避免子类忘记加入 Adapter
    2. 抽象方法确保子类实现核心功能
    3. 职责分离：Adapter 负责协议，Role 负责业务
    4. handle() 方法作为主入口，处理完整流程
    """
    
    def __init__(self, adapter: Adapter):
        """
        初始化角色
        
        Args:
            adapter: 适配器实例，必须继承自 Adapter
            
        Raises:
            TypeError: 如果 adapter 不是 Adapter 类型
        """
        if not isinstance(adapter, Adapter):
            raise TypeError(f"Role must hold an Adapter instance, got {type(adapter)}")
        
        self._adapter = adapter
        self._role_id: Optional[str] = None
    
    @property
    def adapter(self) -> Adapter:
        """获取适配器实例"""
        return self._adapter
    
    @property
    def role_id(self) -> Optional[str]:
        """获取角色 ID（注册后可用）"""
        return self._role_id
    
    @role_id.setter
    def role_id(self, value: str):
        """设置角色 ID（由 RoleManager 调用）"""
        self._role_id = value
    
    @abstractmethod
    def get_role_id(self) -> str:
        """
        获取角色 ID（子类必须实现）
        
        注意：如果尚未注册，应该返回预定义的 ID（如 "tool:xxx"）
        """
        pass
    
    @abstractmethod
    def get_role_type(self) -> str:
        """
        获取角色类型（子类必须实现）
        
        示例："llm", "user", "tool", "system"
        """
        pass
    
    def get_role_group(self) -> Optional[str]:
        """
        获取角色组（子类可重写）
        """
        return None
    
    def get_labels(self) -> List[str]:
        """
        获取标签列表（子类可重写）
        """
        return []
    
    def get_metadata(self) -> Dict[str, Any]:
        """
        获取元数据（子类可重写）
        """
        return {}
    
    def to_role_data(self) -> RoleData:
        """
        转换为注册数据格式
        """
        return RoleData(
            role_id=self.get_role_id(),
            role_type=self.get_role_type(),
            role_group=self.get_role_group(),
            labels=self.get_labels(),
            metadata=self.get_metadata(),
            is_active=True
        )
    
    def register(self, server: "MCPServer") -> bool:
        """
        注册到 MCP Server（调用 Adapter）
        """
        success = self._adapter._register(server)
        if success and self._role_id is None:
            self._role_id = self.get_role_id()
        return success
    
    def unregister(self, server: "MCPServer") -> bool:
        """
        从 MCP Server 注销（调用 Adapter）
        """
        return self._adapter._unregister(server)

    @abstractmethod
    def handle(self, context: Any) -> Any:
        """
        处理 MCP 消息
        
        处理流程：
        1. unwrap_mcp() - 解析 MCP 消息
        2. handle() - 根据上下文判断环节，调用对应内部方法
        3. wrap_mcp() - 封装返回消息
        
        Args:
            context: unwrap_mcp() 解析得到的 MCP 上下文
        
        Returns:
            处理结果，将传给 wrap_mcp()
        """
        pass


# ============================================================
# 角色信息存储类（与业务 Role 分离）
# ============================================================

class RoleInfo:
    """
    角色信息存储类
    
    设计说明：
    1. 用于存储角色的元数据（用于权限管理、查询等）
    2. 与业务 Role 分离，避免耦合
    3. 支持未来的数据库存储
    """
    
    def __init__(
        self,
        role_id: str,
        role_type: str,
        role_group: Optional[str] = None,
        labels: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        created_at: Optional[str] = None,
        updated_at: Optional[str] = None,
        is_active: bool = True
    ):
        self.role_id = role_id
        self.role_type = role_type
        self.role_group = role_group
        self.labels = labels or []
        self.metadata = metadata or {}
        self.created_at = created_at or datetime.utcnow().isoformat()
        self.updated_at = updated_at or datetime.utcnow().isoformat()
        self.is_active = is_active
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "role_id": self.role_id,
            "role_type": self.role_type,
            "role_group": self.role_group,
            "labels": self.labels,
            "metadata": self.metadata,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "is_active": self.is_active
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RoleInfo":
        return cls(
            role_id=data["role_id"],
            role_type=data["role_type"],
            role_group=data.get("role_group"),
            labels=data.get("labels", []),
            metadata=data.get("metadata", {}),
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at"),
            is_active=data.get("is_active", True)
        )
    
    @classmethod
    def from_role_data(cls, role_data: RoleData) -> "RoleInfo":
        return cls(
            role_id=role_data.role_id,
            role_type=role_data.role_type,
            role_group=role_data.role_group,
            labels=role_data.labels,
            metadata=role_data.metadata,
            created_at=role_data.created_at,
            updated_at=role_data.updated_at,
            is_active=role_data.is_active
        )
    
    def update(self, **kwargs) -> None:
        for key, value in kwargs.items():
            if hasattr(self, key):
                setattr(self, key, value)
        self.updated_at = datetime.utcnow().isoformat()
    
    def add_label(self, label: str) -> None:
        if label not in self.labels:
            self.labels.append(label)
            self.updated_at = datetime.utcnow().isoformat()
    
    def remove_label(self, label: str) -> None:
        if label in self.labels:
            self.labels.remove(label)
            self.updated_at = datetime.utcnow().isoformat()
    
    def has_label(self, label: str) -> bool:
        return label in self.labels
    
    def deactivate(self) -> None:
        self.is_active = False
        self.updated_at = datetime.utcnow().isoformat()
    
    def activate(self) -> None:
        self.is_active = True
        self.updated_at = datetime.utcnow().isoformat()


# ============================================================
# RoleManager（角色管理器）
# ============================================================

class RoleManager:
    """
    角色管理器
    
    功能：
    1. 管理角色的注册/注销
    2. 管理角色组
    3. 支持各种查询
    4. 自动调用 Role 的 Adapter 进行注册/注销
    """
    
    def __init__(self):
        self.role_infos: Dict[str, RoleInfo] = {}
        self.role_instances: Dict[str, Role] = {}
        self.role_groups: Dict[str, List[str]] = {}
    
    def register_role(self, role: Role, server: "MCPServer") -> str:
        """
        注册角色实例
        
        Args:
            role: 角色实例（必须继承自 Role）
            server: MCP Server 实例
            
        Returns:
            角色 ID
            
        注意：自动调用 role.register() 进行注册
        """
        # 获取角色数据
        role_data = role.to_role_data()
        role_id = role_data.role_id
        
        # 创建角色信息
        role_info = RoleInfo.from_role_data(role_data)
        
        # 存储角色信息
        self.role_infos[role_id] = role_info
        self.role_instances[role_id] = role
        
        # 设置角色的 role_id
        role.role_id = role_id
        
        # 更新角色组
        if role_info.role_group:
            if role_info.role_group not in self.role_groups:
                self.role_groups[role_info.role_group] = []
            if role_id not in self.role_groups[role_info.role_group]:
                self.role_groups[role_info.role_group].append(role_id)
        
        # 调用角色的注册方法
        role.register(server)
        
        return role_id
    
    def unregister_role(self, role_id: str, server: "MCPServer") -> bool:
        """
        注销角色
        
        Args:
            role_id: 角色 ID
            server: MCP Server 实例
            
        Returns:
            是否成功注销
            
        注意：自动调用 role.unregister() 进行注销
        """
        if role_id not in self.role_infos:
            return False
        
        # 获取角色实例
        role = self.role_instances.get(role_id)
        
        # 调用角色的注销方法
        if role:
            role.unregister(server)
        
        # 清理角色组
        role_info = self.role_infos[role_id]
        if role_info.role_group and role_info.role_group in self.role_groups:
            if role_id in self.role_groups[role_info.role_group]:
                self.role_groups[role_info.role_group].remove(role_id)
        
        # 移除存储
        del self.role_infos[role_id]
        if role_id in self.role_instances:
            del self.role_instances[role_id]
        
        return True
    
    def get_role(self, role_id: str) -> Optional[Role]:
        """
        获取角色实例
        """
        return self.role_instances.get(role_id)
    
    def get_role_info(self, role_id: str) -> Optional[RoleInfo]:
        """
        获取角色信息
        """
        return self.role_infos.get(role_id)
    
    def get_roles_by_type(self, role_type: str) -> List[Role]:
        """
        按类型获取角色列表
        """
        result = []
        for role_info in self.role_infos.values():
            if role_info.role_type == role_type:
                role = self.role_instances.get(role_info.role_id)
                if role:
                    result.append(role)
        return result
    
    def get_roles_by_group(self, role_group: str) -> List[Role]:
        """
        按角色组获取角色列表
        """
        role_ids = self.role_groups.get(role_group, [])
        return [self.role_instances[rid] for rid in role_ids if rid in self.role_instances]
    
    def get_roles_by_label(self, label: str) -> List[Role]:
        """
        按标签获取角色列表
        """
        result = []
        for role_info in self.role_infos.values():
            if role_info.has_label(label):
                role = self.role_instances.get(role_info.role_id)
                if role:
                    result.append(role)
        return result
    
    def update_role(self, role_id: str, **kwargs) -> bool:
        """
        更新角色信息
        """
        role_info = self.get_role_info(role_id)
        if not role_info:
            return False
        
        old_group = role_info.role_group
        role_info.update(**kwargs)
        
        # 如果角色组变化，更新角色组映射
        if "role_group" in kwargs and kwargs["role_group"] != old_group:
            if old_group and old_group in self.role_groups:
                if role_id in self.role_groups[old_group]:
                    self.role_groups[old_group].remove(role_id)
            
            new_group = kwargs["role_group"]
            if new_group:
                if new_group not in self.role_groups:
                    self.role_groups[new_group] = []
                if role_id not in self.role_groups[new_group]:
                    self.role_groups[new_group].append(role_id)
        
        return True
    
    def list_all_roles(self) -> Dict[str, Dict[str, Any]]:
        """
        列出所有角色信息
        """
        return {rid: role_info.to_dict() for rid, role_info in self.role_infos.items()}
    
    def list_all_groups(self) -> Dict[str, List[str]]:
        """
        列出所有角色组
        """
        return self.role_groups.copy()
