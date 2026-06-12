from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional, Dict, Any
import logging
import asyncio
import json

logger = logging.getLogger(__name__)

router = APIRouter()

_mcp_http_transport = None


class MessageRequest(BaseModel):
    message: str


class MessageResponse(BaseModel):
    response: str
    mcp_used: Optional[str] = None


class MCPMessageRequest(BaseModel):
    source_id: Optional[str] = None
    target_id: Optional[str] = None
    content: str


@router.post("/message", response_model=MessageResponse)
async def handle_message(request: Request):
    logger.info(f"收到请求 - 路径: {request.url.path}")
    
    try:
        json_body = await request.json()
        message = json_body.get("message", "")
        logger.info(f"提取的message字段: '{message}'")
    except Exception as e:
        logger.error(f"解析JSON失败: {e}")
        raise HTTPException(status_code=400, detail=f"无法解析JSON: {str(e)}")
    
    # 优先使用 MCP 系统的消息处理器
    from ..mcp import get_server, MCPMessage
    
    try:
        server = get_server()
        
        # 创建 MCP 消息
        mcp_message = MCPMessage.create_user_message(
            user_id="mcp:client",
            user_group="clients",
            content=message,
            target_id="agent:default-agent",
            target_type="agent"
        )
        
        # 使用 MCP 服务器处理消息
        response = await server.process(mcp_message)
        
        final_response = response.payload.raw_content or "抱歉，处理失败"
        logger.info(f"[API] 返回给游戏客户端: {final_response}")
        
        return MessageResponse(
            response=final_response,
            mcp_used="mcp_server"
        )
    except Exception as e:
        logger.error(f"MCP 处理失败，回退到 Agent: {e}")
        import traceback
        traceback.print_exc()
        
        # 回退到 Agent
        from ..llm.agent import get_agent
        agent = get_agent()
        
        try:
            response = await agent.process_message(message)
            return MessageResponse(
                response=response,
                mcp_used="llm_agent"
            )
        except Exception as e2:
            logger.error(f"处理消息失败: {e2}")
            raise HTTPException(status_code=500, detail=str(e2))


@router.post("/mcp/message")
async def handle_mcp_message(request: MCPMessageRequest):
    from ..mcp import get_server, MCPMessage
    from ..mcp.setup import get_scaffold
    
    scaffold = get_scaffold()
    server = get_server()
    
    # 默认使用 MCP 客户端接口作为来源
    source_id = request.source_id or "mcp:client"
    target_id = request.target_id or "agent:default-agent"
    
    message = MCPMessage.create_user_message(
        user_id=source_id,
        user_group="clients",
        content=request.content,
        target_id=target_id,
        target_type="llm"
    )
    
    try:
        response = await server.process(message)
        
        return {
            "success": True,
            "message_id": message.message_id,
            "response": response.payload.raw_content,
            "source": response.source.to_dict() if response.source else None,
            "target": response.target.to_dict() if response.target else None
        }
    except Exception as e:
        logger.error(f"MCP消息处理失败: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/mcp/roles")
async def list_roles():
    from ..mcp import get_server
    
    server = get_server()
    return server.list_roles()


@router.get("/mcp/tools")
async def list_tools():
    from ..mcp import get_server
    
    server = get_server()
    return server.list_tools()


@router.get("/mcp/permissions")
async def list_permissions():
    from ..mcp import get_server
    
    server = get_server()
    return server.list_permissions()


@router.get("/mcp/stats")
async def get_stats():
    from ..mcp import get_audit_logger
    
    audit_logger = get_audit_logger()
    return audit_logger.get_stats()


@router.get("/mcps")
async def list_mcps():
    from ..mcp import get_server
    
    server = get_server()
    return server.list_tools()


# === Anthropic MCP 标准端点 ===

@router.post("/mcp/v1")
async def mcp_jsonrpc(request: Request):
    global _mcp_http_transport
    if _mcp_http_transport is None:
        raise HTTPException(status_code=503, detail="MCP transport not initialized")

    raw_body = await request.body()
    try:
        raw_str = raw_body.decode("utf-8")
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid request body")

    accept = request.headers.get("accept", "")
    if "text/event-stream" in accept:
        return StreamingResponse(
            _mcp_sse_generator(raw_str),
            media_type="text/event-stream",
        )

    result = await _mcp_http_transport.handle_post(raw_str)
    if not result:
        return {}
    try:
        return json.loads(result)
    except json.JSONDecodeError:
        return {"raw": result}


async def _mcp_sse_generator(raw_str: str):
    queue = asyncio.Queue()
    _mcp_http_transport.register_sse_client(queue)

    result = await _mcp_http_transport.handle_post(raw_str)
    if result:
        yield f"event: message\ndata: {result}\n\n"

    try:
        while True:
            data = await asyncio.wait_for(queue.get(), timeout=30)
            yield f"event: message\ndata: {data}\n\n"
    except asyncio.TimeoutError:
        yield f"event: ping\ndata: {{}}\n\n"
    finally:
        _mcp_http_transport.unregister_sse_client(queue)


def init_mcp_transport():
    global _mcp_http_transport
    from ..mcp.server import get_server
    from ..mcp.external.server import MCPServerAdapter
    adapter = MCPServerAdapter(get_server())
    _mcp_http_transport = adapter.create_http_transport()
    logger.info("MCP HTTP transport initialized")


# === 脚手架管理接口 ===

class RegisterBuiltinRequest(BaseModel):
    builtin_name: str
    role_config: Optional[Dict[str, Any]] = None


class UnregisterRequest(BaseModel):
    role_id: str
    force: bool = False


class UnregisterByLabelRequest(BaseModel):
    label: str


@router.get("/scaffold/roles")
async def list_scaffold_roles():
    """获取所有已注册的角色"""
    from ..mcp.setup import get_scaffold
    
    scaffold = get_scaffold()
    return {
        "registered_roles": scaffold.get_registered_roles(),
        "builtin_roles": scaffold.get_builtin_roles()
    }


@router.post("/scaffold/unregister")
async def unregister_role(request: UnregisterRequest):
    """注销指定角色"""
    from ..mcp.setup import get_scaffold
    
    scaffold = get_scaffold()
    try:
        result = scaffold.unregister(request.role_id, request.force)
        return {"success": result, "unregistered": request.role_id}
    except Exception as e:
        logger.error(f"注销失败: {e}")
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/scaffold/unregister-by-label")
async def unregister_by_label(request: UnregisterByLabelRequest):
    """基于标签注销角色"""
    from ..mcp.setup import get_scaffold
    
    scaffold = get_scaffold()
    try:
        unregistered = scaffold.unregister_by_label(request.label)
        return {"success": True, "unregistered": unregistered}
    except Exception as e:
        logger.error(f"基于标签注销失败: {e}")
        raise HTTPException(status_code=400, detail=str(e))