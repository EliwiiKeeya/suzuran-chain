import uvicorn
import logging
from suzuran_chain.main import app
from suzuran_chain.config import get_settings

# 设置日志级别
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

if __name__ == "__main__":
    settings = get_settings()
    uvicorn.run(
        "suzuran_chain.main:app",
        host=settings.backend_host,
        port=settings.backend_port,
        reload=True,
        log_level="info"
    )
