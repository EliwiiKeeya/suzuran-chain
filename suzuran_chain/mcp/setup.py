"""
MCP 设置模块

提供脚手架初始化函数
"""
import logging
from .config import LLMConfig
from .scaffold import MCPScaffold
from .server import get_server

logger = logging.getLogger(__name__)

# 全局脚手架实例
_scaffold: MCPScaffold = None


def create_mcp_scaffold(llm_config: LLMConfig) -> MCPScaffold:
    """
    创建 MCP 脚手架

    快速开始：只需提供 LLM 配置即可获得完整的后端

    Args:
        llm_config: LLM 配置

    Returns:
        MCPScaffold 实例
    """
    global _scaffold

    # 验证配置
    llm_config.validate()

    # 创建脚手架
    _scaffold = MCPScaffold(llm_config)

    return _scaffold


def get_scaffold() -> MCPScaffold:
    """
    获取全局脚手架实例

    Returns:
        MCPScaffold 实例

    Raises:
        RuntimeError: 如果脚手架尚未初始化
    """
    if _scaffold is None:
        raise RuntimeError("MCP Scaffold not initialized. Call create_mcp_scaffold() first.")
    return _scaffold


def setup_mcp_server():
    """
    向后兼容：使用默认配置创建脚手架
    """
    logger.warning("setup_mcp_server() is deprecated. Use create_mcp_scaffold() instead.")
    config = LLMConfig.from_env()
    return create_mcp_scaffold(config)
