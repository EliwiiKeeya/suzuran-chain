"""
MCP 配置模块

定义 LLM 配置和其他核心配置
"""
from dataclasses import dataclass
from typing import Optional, Dict, Any


@dataclass
class LLMConfig:
    """
    LLM 配置类

    用于配置 AI 助手的连接信息
    """
    # 基础配置
    api_url: str  # LLM API 地址
    model: str    # 模型名称
    api_key: str  # API 密钥

    # 可选配置
    temperature: float = 0.7
    max_tokens: int = 2048
    timeout: int = 60
    extra_params: Optional[Dict[str, Any]] = None

    @classmethod
    def from_dict(cls, config: Dict[str, Any]) -> 'LLMConfig':
        """从字典创建配置"""
        return cls(
            api_url=config.get('api_url', ''),
            model=config.get('model', ''),
            api_key=config.get('api_key', ''),
            temperature=config.get('temperature', 0.7),
            max_tokens=config.get('max_tokens', 2048),
            timeout=config.get('timeout', 60),
            extra_params=config.get('extra_params')
        )

    @classmethod
    def from_env(cls) -> 'LLMConfig':
        """从环境变量创建配置"""
        import os
        
        # 支持两种变量命名方式，优先使用 LLM_ 前缀，其次是 OPENAI_ 前缀
        api_url = os.getenv('LLM_API_URL') or os.getenv('OPENAI_BASE_URL', '')
        model = os.getenv('LLM_MODEL') or os.getenv('OPENAI_MODEL', '')
        api_key = os.getenv('LLM_API_KEY') or os.getenv('OPENAI_API_KEY', '')
        
        return cls(
            api_url=api_url,
            model=model,
            api_key=api_key,
            temperature=float(os.getenv('LLM_TEMPERATURE', '0.7')),
            max_tokens=int(os.getenv('LLM_MAX_TOKENS', '2048')),
            timeout=int(os.getenv('LLM_TIMEOUT', '60'))
        )

    def validate(self) -> bool:
        """验证配置是否有效"""
        if not self.api_url:
            raise ValueError("LLM API URL is required")
        if not self.model:
            raise ValueError("LLM model name is required")
        if not self.api_key:
            raise ValueError("LLM API key is required")
        return True
