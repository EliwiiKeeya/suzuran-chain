from typing import Dict, Type
from .base import BaseMCP

class MCPRegistry:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._mcps: Dict[str, BaseMCP] = {}
            cls._instance._register_default_mcps()
        return cls._instance
    
    def _register_default_mcps(self):
        pass
    
    def register(self, mcp: BaseMCP) -> None:
        self._mcps[mcp.name] = mcp
    
    def get(self, name: str) -> BaseMCP:
        if name not in self._mcps:
            raise ValueError(f"MCP '{name}' not found")
        return self._mcps[name]
    
    def list_all(self) -> Dict[str, Dict[str, str]]:
        return {name: mcp.get_info() for name, mcp in self._mcps.items()}
    
    async def execute(self, name: str, **kwargs):
        mcp = self.get(name)
        return await mcp.execute(**kwargs)

def get_registry() -> MCPRegistry:
    return MCPRegistry()
