from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .api.routes import router as api_router
from .config import get_settings
from dotenv import load_dotenv
import logging

logger = logging.getLogger(__name__)

# Load environment variables from .env file
load_dotenv()


def create_app() -> FastAPI:
    settings = get_settings()
    
    app = FastAPI(
        title="Suzuran Chain",
        description="Minecraft Agent Backend Service with MCP Support",
        version="2.0.0"
    )
    
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    app.include_router(api_router, prefix="/api")
    
    @app.on_event("startup")
    async def startup_event():
        from .mcp.config import LLMConfig
        from .mcp.setup import create_mcp_scaffold
        from .mcp import get_audit_logger
        
        # 快速开始：使用 LLM 配置创建脚手架
        llm_config = LLMConfig.from_env()
        
        logger.info("=" * 60)
        logger.info("LLM Configuration:")
        logger.info(f"  API URL: {llm_config.api_url}")
        logger.info(f"  Model: {llm_config.model}")
        logger.info(f"  API Key: {llm_config.api_key[:10]}...")
        logger.info("=" * 60)
        
        scaffold = create_mcp_scaffold(llm_config)
        
        # 注册内置功能
        from .rag.wiki import WikiRAG
        from .mcp.server import get_server
        
        wiki_rag = WikiRAG()
        rag_id = scaffold.register_builtin(wiki_rag)
        
        logger.info(f"✅ 已注册 WikiRAG: {rag_id}")
        
        # 配置完整权限（双向）
        server = get_server()
        
        # 配置权限：mcp:client -> agent:default-agent
        server.grant_permission("mcp:client", "agent:default-agent", ["execute"])
        # 配置权限：agent:default-agent -> rag:wiki
        server.grant_permission("agent:default-agent", rag_id, ["execute"])
        # 配置权限：rag:wiki -> agent:default-agent（反向，用于返回结果）
        server.grant_permission(rag_id, "agent:default-agent", ["execute"])
        
        logger.info(f"✅ 已配置权限")
        logger.info(f"当前权限配置: {server.list_permissions()}")
        
        # 注册 Agent 消息处理器
        from .mcp.scaffold import handle_llm_message
        server.register_message_handler("llm", handle_llm_message)
        server.register_message_handler("agent", handle_llm_message)
        logger.info(f"✅ 已注册 Agent 消息处理器")
        
        # 初始化 Anthropic MCP 标准接口
        from .api.routes import init_mcp_transport
        init_mcp_transport()
        logger.info(f"✅ MCP 标准接口已初始化 (/api/mcp/v1)")
        
        audit_logger = get_audit_logger()
        await audit_logger.start()
        
        logger.info("Suzuran Chain MCP Scaffold initialized")
        logger.info(f"已注册角色: {scaffold.get_registered_roles()}")
    
    @app.on_event("shutdown")
    async def shutdown_event():
        from .mcp import get_audit_logger
        
        audit_logger = get_audit_logger()
        await audit_logger.stop()
        
        logger.info("Suzuran Chain MCP Server shutdown")
    
    @app.get("/")
    async def root():
        return {
            "service": "Suzuran Chain",
            "version": "2.0.0",
            "status": "running",
            "mcp_enabled": True,
            "endpoints": {
                "legacy": "/api/message",
                "mcp": "/api/mcp/message",
                "roles": "/api/mcp/roles",
                "tools": "/api/mcp/tools",
                "permissions": "/api/mcp/permissions",
                "stats": "/api/mcp/stats"
            }
        }
    
    return app


app = create_app()