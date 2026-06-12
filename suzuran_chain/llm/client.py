from openai import AsyncOpenAI
from typing import List, Dict, Any
from ..config import get_settings

class LLMClient:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            settings = get_settings()
            cls._instance.client = AsyncOpenAI(
                api_key=settings.openai_api_key,
                base_url=settings.openai_base_url
            )
            cls._instance.model = settings.openai_model
        return cls._instance
    
    async def chat(
        self,
        messages: List[Dict[str, str]],
        tools: List[Dict[str, Any]] = None,
        tool_choice: str = "auto"
    ) -> Dict[str, Any]:
        params = {
            "model": self.model,
            "messages": messages
        }
        
        if tools:
            params["tools"] = tools
            params["tool_choice"] = tool_choice
        
        response = await self.client.chat.completions.create(**params)
        
        result = {
            "content": response.choices[0].message.content,
            "role": response.choices[0].message.role
        }
        
        if response.choices[0].message.tool_calls:
            result["tool_calls"] = [
                {
                    "id": tc.id,
                    "name": tc.function.name,
                    "arguments": tc.function.arguments
                }
                for tc in response.choices[0].message.tool_calls
            ]
        
        return result
    
    async def simple_chat(self, user_message: str, system_prompt: str = None) -> str:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": user_message})
        
        result = await self.chat(messages)
        return result["content"]

def get_llm_client() -> LLMClient:
    return LLMClient()
