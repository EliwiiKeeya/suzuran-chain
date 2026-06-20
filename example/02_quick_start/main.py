from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
import os
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()

app = FastAPI(title="Quick Start Example", version="1.0.0")


class MessageRequest(BaseModel):
    message: str

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup_event():
    from suzuran_chain.mcp.config import LLMConfig
    from suzuran_chain.mcp.setup import create_mcp_scaffold, get_scaffold
    from suzuran_chain.rag.wiki import WikiRAG
    from suzuran_chain.mcp.server import get_server

    llm_config = LLMConfig.from_env()
    
    logger.info("=" * 60)
    logger.info("LLM Configuration:")
    logger.info(f"  API URL: {llm_config.api_url}")
    logger.info(f"  Model: {llm_config.model}")
    logger.info("=" * 60)

    scaffold = create_mcp_scaffold(llm_config)
    
    wiki_rag = WikiRAG()
    rag_id = scaffold.register_builtin(wiki_rag)
    
    logger.info(f"✅ 已注册 WikiRAG: {rag_id}")
    
    server = get_server()
    server.grant_permission(rag_id, "agent:default-agent", ["execute"])
    
    logger.info("✅ 已配置权限")
    logger.info(f"当前角色: {scaffold.get_registered_roles()}")


@app.post("/api/message")
async def handle_message(request: MessageRequest):
    from suzuran_chain.mcp import get_server, MCPMessage

    server = get_server()

    mcp_message = MCPMessage.create_user_message(
        user_id="mcp:client",
        user_group="clients",
        content=request.message,
        target_id="agent:default-agent",
        target_type="agent"
    )

    response = await server.process(mcp_message)
    
    return {"response": response.payload.raw_content}


@app.get("/")
async def root():
    from suzuran_chain.mcp.setup import get_scaffold
    
    scaffold = get_scaffold()
    
    return {
        "service": "Quick Start Example",
        "version": "1.0.0",
        "status": "running",
        "registered_roles": scaffold.get_registered_roles(),
        "builtin_roles": scaffold.get_builtin_roles(),
        "endpoints": {
            "message": "/api/message",
            "docs": "/docs",
            "roles": "/api/roles",
            "permissions": "/api/permissions"
        }
    }


@app.get("/api/roles")
async def list_roles():
    from suzuran_chain.mcp.setup import get_scaffold
    
    scaffold = get_scaffold()
    return {"roles": scaffold.get_registered_roles()}


@app.get("/api/permissions")
async def list_permissions():
    from suzuran_chain.mcp.server import get_server
    
    server = get_server()
    return {"permissions": server.list_permissions()}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
