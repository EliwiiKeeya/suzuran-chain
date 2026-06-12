from typing import Dict, Any, List
from .base import BaseRAG, RAGAdapter
import logging

# 设置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class WikiRAG(BaseRAG):
    """
    Wiki RAG 实现（仅支持简体中文）

    功能：
    1. 检索 Minecraft Wiki 中文版
    2. 返回检索结果作为 Resource
    """

    # 仅简体中文
    WIKI_API = "https://zh.minecraft.wiki/api.php"

    def __init__(
        self,
        name: str = "wiki",
        description: str = "检索 Minecraft Wiki 获取游戏知识"
    ):
        adapter = RAGAdapter(self)
        super().__init__(adapter)
        self.name = name
        self.description = description

    async def retrieve(self, query: str, **kwargs) -> str:
        """
        执行 Wiki 检索

        Args:
            query: 检索查询

        Returns:
            检索结果内容
        """
        logger.info(f"WikiRAG 收到检索请求: query='{query}', kwargs={kwargs}")
        
        try:
            import httpx

            async with httpx.AsyncClient(timeout=10.0) as client:
                search_url = f"{self.WIKI_API}?action=query&list=search&srsearch={query}&format=json"
                logger.info(f"搜索 URL: {search_url}")
                search_response = await client.get(search_url)
                search_data = search_response.json()
                logger.info(f"搜索响应状态码: {search_response.status_code}")

                titles = self._parse_search_results(search_data)
                logger.info(f"解析到标题: {titles}")
                if not titles:
                    return "未找到相关 Wiki 条目"

                title = titles[0]
                logger.info(f"获取页面: {title}")
                extract_url = (
                    f"{self.WIKI_API}?action=query&titles={title}"
                    f"&prop=extracts&explaintext=true&format=json"
                )
                logger.info(f"页面 URL: {extract_url}")
                extract_response = await client.get(extract_url)
                extract_data = extract_response.json()
                logger.info(f"页面响应状态码: {extract_response.status_code}")

                return self._parse_page_extract(extract_data, title)
        except ImportError:
            logger.warning("httpx 不可用")
            return f"RAG 查询失败: httpx 不可用"
        except Exception as e:
            logger.error(f"Wiki API 请求失败: {e}")
            return f"Wiki 查询失败: {e}"

    def _parse_search_results(self, data: Dict[str, Any]) -> List[str]:
        """解析搜索结果，返回标题列表"""
        logger.info(f"解析搜索数据: {data}")
        query = data.get("query", {})
        search = query.get("search", [])
        logger.info(f"搜索结果: {search}")
        return [item["title"] for item in search[:3]]

    def _parse_page_extract(self, data: Dict[str, Any], fallback_title: str) -> str:
        """解析页面摘要"""
        logger.info(f"解析页面数据: {data}")
        query = data.get("query", {})
        pages = query.get("pages", {})
        logger.info(f"页面: {pages}")

        for page_id, page_data in pages.items():
            if page_id != "-1":
                extract = page_data.get("extract", "")
                if extract:
                    logger.info(f"获取到摘要: {len(extract)} 字符")
                    return extract[:4000]  # 截断到合理长度

        logger.warning(f"无法获取 '{fallback_title}' 的详细信息")
        return f"无法获取 '{fallback_title}' 的详细信息"

    def get_role_id(self) -> str:
        return self.role_id or f"rag:wiki"

    def get_resource_type(self) -> str:
        return "wiki"
