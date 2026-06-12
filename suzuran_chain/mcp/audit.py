from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from datetime import datetime
import uuid
import json
import asyncio
import logging

logger = logging.getLogger(__name__)


@dataclass
class CallLog:
    # ============================================================
    # 冗余设计说明 (2026-05-26):
    # 审计日志系统预留了以下扩展点：
    #
    # 1. 异步日志队列:
    #    - 使用 asyncio.Queue 实现异步写入
    #    - 支持未来切换到数据库（MySQL/PostgreSQL/MongoDB）
    #    - 支持批量写入优化性能
    #
    # 2. metadata: 扩展字段，支持存储额外审计信息
    #    - 未来可存储: IP 地址、用户代理、调用链路等
    #
    # 3. audit_level: 审计级别
    #    - "low": 只记录基本调用
    #    - "medium": 记录请求/响应内容
    #    - "high": 记录完整调用链和错误详情
    #
    # 4. max_logs: 日志数量上限
    #    - 内存不足时可切换到磁盘存储
    #    - 支持日志轮转和归档
    #
    # 5. duration_ms: 调用耗时统计
    #    - 支持性能监控和告警
    #
    # 注意：当前使用内存存储，未来应迁移到数据库
    # ============================================================
    log_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    message_id: str = ""
    source_role_id: str = ""
    target_role_id: str = ""
    action: str = ""
    request: Dict[str, Any] = field(default_factory=dict)
    response: Dict[str, Any] = field(default_factory=dict)
    status: str = "pending"
    duration_ms: int = 0
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    completed_at: Optional[str] = None
    audit_level: str = "low"
    error_message: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "log_id": self.log_id,
            "message_id": self.message_id,
            "source_role_id": self.source_role_id,
            "target_role_id": self.target_role_id,
            "action": self.action,
            "request": self.request,
            "response": self.response,
            "status": self.status,
            "duration_ms": self.duration_ms,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
            "audit_level": self.audit_level,
            "error_message": self.error_message,
            "metadata": self.metadata
        }
    
    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CallLog":
        return cls(
            log_id=data.get("log_id", str(uuid.uuid4())),
            message_id=data.get("message_id", ""),
            source_role_id=data.get("source_role_id", ""),
            target_role_id=data.get("target_role_id", ""),
            action=data.get("action", ""),
            request=data.get("request", {}),
            response=data.get("response", {}),
            status=data.get("status", "pending"),
            duration_ms=data.get("duration_ms", 0),
            created_at=data.get("created_at", datetime.utcnow().isoformat()),
            completed_at=data.get("completed_at"),
            audit_level=data.get("audit_level", "low"),
            error_message=data.get("error_message"),
            metadata=data.get("metadata", {})
        )


class AuditLogger:
    def __init__(self, max_logs: int = 10000):
        self.logs: Dict[str, CallLog] = {}
        self.max_logs = max_logs
        self.pending_logs: asyncio.Queue = asyncio.Queue()
        self._worker_task: Optional[asyncio.Task] = None
    
    async def start(self) -> None:
        if self._worker_task is None:
            self._worker_task = asyncio.create_task(self._process_logs())
            logger.info("Audit logger started")
    
    async def stop(self) -> None:
        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass
            self._worker_task = None
            logger.info("Audit logger stopped")
    
    async def _process_logs(self) -> None:
        while True:
            try:
                log = await self.pending_logs.get()
                await self._write_log(log)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error processing audit log: {e}")
    
    async def _write_log(self, log: CallLog) -> None:
        if len(self.logs) >= self.max_logs:
            oldest_id = min(self.logs.keys(), key=lambda k: self.logs[k].created_at)
            del self.logs[oldest_id]
        
        self.logs[log.log_id] = log
        
        if log.audit_level == "high":
            logger.info(f"[AUDIT] {log.action}: {log.source_role_id} -> {log.target_role_id} ({log.status})")
    
    async def log(self, call_log: CallLog) -> None:
        await self.pending_logs.put(call_log)
    
    async def log_call(
        self,
        message_id: str,
        source_role_id: str,
        target_role_id: str,
        action: str,
        request: Dict[str, Any],
        audit_level: str = "low"
    ) -> str:
        log = CallLog(
            message_id=message_id,
            source_role_id=source_role_id,
            target_role_id=target_role_id,
            action=action,
            request=request,
            status="pending",
            audit_level=audit_level
        )
        
        await self.log(log)
        return log.log_id
    
    async def complete_call(
        self,
        log_id: str,
        response: Dict[str, Any],
        status: str = "success",
        error_message: Optional[str] = None
    ) -> None:
        if log_id not in self.logs:
            logger.warning(f"Log not found: {log_id}")
            return
        
        log = self.logs[log_id]
        log.response = response
        log.status = status
        log.error_message = error_message
        log.completed_at = datetime.utcnow().isoformat()
        
        created_time = datetime.fromisoformat(log.created_at)
        completed_time = datetime.fromisoformat(log.completed_at)
        log.duration_ms = int((completed_time - created_time).total_seconds() * 1000)
    
    async def query(
        self,
        source_role_id: Optional[str] = None,
        target_role_id: Optional[str] = None,
        action: Optional[str] = None,
        status: Optional[str] = None,
        audit_level: Optional[str] = None,
        limit: int = 100
    ) -> List[CallLog]:
        results = []
        
        for log in sorted(self.logs.values(), key=lambda l: l.created_at, reverse=True):
            if source_role_id and log.source_role_id != source_role_id:
                continue
            if target_role_id and log.target_role_id != target_role_id:
                continue
            if action and log.action != action:
                continue
            if status and log.status != status:
                continue
            if audit_level and log.audit_level != audit_level:
                continue
            
            results.append(log)
            
            if len(results) >= limit:
                break
        
        return results
    
    def get_log(self, log_id: str) -> Optional[CallLog]:
        return self.logs.get(log_id)
    
    def get_stats(self) -> Dict[str, Any]:
        total = len(self.logs)
        success = sum(1 for log in self.logs.values() if log.status == "success")
        failed = sum(1 for log in self.logs.values() if log.status == "failed")
        pending = sum(1 for log in self.logs.values() if log.status == "pending")
        
        avg_duration = 0
        if total > 0:
            durations = [log.duration_ms for log in self.logs.values() if log.duration_ms > 0]
            if durations:
                avg_duration = sum(durations) // len(durations)
        
        return {
            "total_logs": total,
            "success_count": success,
            "failed_count": failed,
            "pending_count": pending,
            "average_duration_ms": avg_duration,
            "max_logs": self.max_logs
        }


_audit_logger: Optional[AuditLogger] = None


def get_audit_logger() -> AuditLogger:
    global _audit_logger
    if _audit_logger is None:
        _audit_logger = AuditLogger()
    return _audit_logger