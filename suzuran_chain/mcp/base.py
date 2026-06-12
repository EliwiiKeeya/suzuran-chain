from abc import ABC, abstractmethod
from typing import Dict, Any

class BaseMCP(ABC):
    def __init__(self, name: str, description: str):
        self.name = name
        self.description = description
    
    @abstractmethod
    async def execute(self, **kwargs) -> Dict[str, Any]:
        pass
    
    def get_info(self) -> Dict[str, str]:
        return {
            "name": self.name,
            "description": self.description
        }
