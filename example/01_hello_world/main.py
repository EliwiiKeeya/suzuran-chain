from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from suzuran_chain.mcp.protocol import Role, Adapter, MCPMessage, MessageSource, MessageTarget, MessagePayload

app = FastAPI(title="Hello World Example", version="1.0.0")


class MessageRequest(BaseModel):
    message: str

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class HelloWorldAdapter(Adapter):
    def __init__(self, role):
        self._role = role

    def _register(self, server) -> bool:
        return True

    def _unregister(self, server) -> bool:
        return True

    def wrap_mcp(self, data) -> MCPMessage:
        return MCPMessage(
            source=MessageSource(role_id=self._role.get_role_id(), role_type=self._role.get_role_type()),
            payload=MessagePayload(raw_content=data)
        )

    def unwrap_mcp(self, message: MCPMessage) -> str:
        return message.payload.raw_content


class HelloWorldRole(Role):
    def __init__(self):
        adapter = HelloWorldAdapter(self)
        super().__init__(adapter)

    def get_role_id(self) -> str:
        return "agent:hello-world"

    def get_role_type(self) -> str:
        return "agent"

    def get_role_group(self):
        return "demo"

    def can_send_message(self) -> bool:
        return True

    def can_receive_message(self) -> bool:
        return True

    def handle(self, context) -> str:
        return "Hello world!"


@app.post("/api/message")
async def handle_message(request: MessageRequest):
    agent = HelloWorldRole()
    context = agent.adapter.unwrap_mcp(
        MCPMessage(
            source=MessageSource(role_id="client", role_type="client"),
            payload=MessagePayload(raw_content=request.message)
        )
    )
    result = agent.handle(context)
    response = agent.adapter.wrap_mcp(result)
    
    return {"response": response.payload.raw_content}


@app.get("/")
async def root():
    return {
        "service": "Hello World Example",
        "version": "1.0.0",
        "endpoints": {
            "message": "/api/message",
            "docs": "/docs"
        }
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
