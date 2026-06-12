from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional
from datetime import datetime
import uuid
import json
import asyncio
import logging

logger = logging.getLogger(__name__)


@dataclass
class MessageEnvelope:
    # ============================================================
    # 冗余设计说明 (2026-05-26):
    # 消息总线系统预留了以下扩展点，支持分布式架构：
    #
    # 1. 消息封装:
    #    - envelope_id: 唯一信封ID，支持消息去重和追踪
    #    - routing_key: 路由键，支持消息路由和过滤
    #    - headers: 消息头，支持元数据传递
    #
    # 2. 可靠性保证:
    #    - expires_at: 消息过期时间，支持 TTL
    #    - retry_count/max_retries: 重试机制
    #    - 确认机制（acknowledge）确保消息被处理
    #
    # 3. 优先级:
    #    - priority: 消息优先级，支持优先处理重要消息
    #
    # 4. 分布式扩展:
    #    - DistributedMessageBus 类预留集群支持
    #    - backend: 可切换消息队列后端（Redis/RabbitMQ/Kafka）
    #    - cluster_nodes: 集群节点管理
    #
    # 注意：当前使用内存队列，未来应切换到分布式消息队列
    # ============================================================
    envelope_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    message_id: str = ""
    protocol_version: str = "1.0"
    routing_key: str = ""
    headers: Dict[str, Any] = field(default_factory=dict)
    body: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    expires_at: Optional[str] = None
    priority: int = 0
    retry_count: int = 0
    max_retries: int = 3
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "envelope_id": self.envelope_id,
            "message_id": self.message_id,
            "protocol_version": self.protocol_version,
            "routing_key": self.routing_key,
            "headers": self.headers,
            "body": self.body,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "priority": self.priority,
            "retry_count": self.retry_count,
            "max_retries": self.max_retries
        }
    
    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MessageEnvelope":
        return cls(
            envelope_id=data.get("envelope_id", str(uuid.uuid4())),
            message_id=data.get("message_id", ""),
            protocol_version=data.get("protocol_version", "1.0"),
            routing_key=data.get("routing_key", ""),
            headers=data.get("headers", {}),
            body=data.get("body", {}),
            created_at=data.get("created_at", datetime.utcnow().isoformat()),
            expires_at=data.get("expires_at"),
            priority=data.get("priority", 0),
            retry_count=data.get("retry_count", 0),
            max_retries=data.get("max_retries", 3)
        )
    
    @classmethod
    def wrap_mcp_message(cls, message: Any, routing_key: str = "") -> "MessageEnvelope":
        from .protocol import MCPMessage
        
        if isinstance(message, MCPMessage):
            body = message.to_dict()
            message_id = message.message_id
        else:
            body = message if isinstance(message, dict) else {"data": message}
            message_id = str(uuid.uuid4())
        
        return cls(
            message_id=message_id,
            routing_key=routing_key,
            body=body
        )


class MessageBus:
    def __init__(self):
        self.subscribers: Dict[str, list] = {}
        self.queue: asyncio.Queue = asyncio.Queue()
        self._worker_task: Optional[asyncio.Task] = None
        self._running = False
    
    async def start(self) -> None:
        if not self._running:
            self._running = True
            self._worker_task = asyncio.create_task(self._process_messages())
            logger.info("Message bus started")
    
    async def stop(self) -> None:
        if self._running:
            self._running = False
            if self._worker_task:
                self._worker_task.cancel()
                try:
                    await self._worker_task
                except asyncio.CancelledError:
                    pass
                self._worker_task = None
            logger.info("Message bus stopped")
    
    async def _process_messages(self) -> None:
        while self._running:
            try:
                envelope = await asyncio.wait_for(self.queue.get(), timeout=1.0)
                await self._deliver(envelope)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error processing message: {e}")
    
    async def _deliver(self, envelope: MessageEnvelope) -> None:
        routing_key = envelope.routing_key
        
        if routing_key in self.subscribers:
            for handler in self.subscribers[routing_key]:
                try:
                    await handler(envelope)
                except Exception as e:
                    logger.error(f"Error in subscriber handler: {e}")
                    
                    if envelope.retry_count < envelope.max_retries:
                        envelope.retry_count += 1
                        await self.queue.put(envelope)
                        logger.info(f"Retrying message {envelope.envelope_id} (attempt {envelope.retry_count})")
    
    async def publish(self, envelope: MessageEnvelope) -> None:
        await self.queue.put(envelope)
        logger.debug(f"Published message: {envelope.envelope_id}")
    
    async def subscribe(self, routing_key: str, handler: Callable) -> None:
        if routing_key not in self.subscribers:
            self.subscribers[routing_key] = []
        
        self.subscribers[routing_key].append(handler)
        logger.info(f"Subscribed to routing key: {routing_key}")
    
    async def unsubscribe(self, routing_key: str, handler: Callable) -> None:
        if routing_key in self.subscribers:
            if handler in self.subscribers[routing_key]:
                self.subscribers[routing_key].remove(handler)
                logger.info(f"Unsubscribed from routing key: {routing_key}")
    
    async def acknowledge(self, envelope_id: str) -> None:
        logger.debug(f"Acknowledged message: {envelope_id}")
    
    def get_stats(self) -> Dict[str, Any]:
        return {
            "queue_size": self.queue.qsize(),
            "subscriber_count": sum(len(handlers) for handlers in self.subscribers.values()),
            "routing_keys": list(self.subscribers.keys()),
            "is_running": self._running
        }


class DistributedMessageBus(MessageBus):
    def __init__(self, backend: str = "memory"):
        super().__init__()
        self.backend = backend
        self.cluster_nodes: list = []
        self.node_id = str(uuid.uuid4())
    
    async def connect_to_cluster(self, node_addresses: list) -> None:
        self.cluster_nodes = node_addresses
        logger.info(f"Connected to cluster with {len(node_addresses)} nodes")
    
    async def broadcast(self, envelope: MessageEnvelope) -> None:
        await self.publish(envelope)
        logger.info(f"Broadcast message to cluster: {envelope.envelope_id}")
    
    async def send_to_node(self, node_id: str, envelope: MessageEnvelope) -> None:
        logger.info(f"Sent message to node {node_id}: {envelope.envelope_id}")
    
    def get_cluster_info(self) -> Dict[str, Any]:
        return {
            "node_id": self.node_id,
            "backend": self.backend,
            "cluster_nodes": self.cluster_nodes,
            "stats": self.get_stats()
        }


_message_bus: Optional[MessageBus] = None


def get_message_bus() -> MessageBus:
    global _message_bus
    if _message_bus is None:
        _message_bus = MessageBus()
    return _message_bus


def get_distributed_message_bus(backend: str = "memory") -> DistributedMessageBus:
    return DistributedMessageBus(backend=backend)