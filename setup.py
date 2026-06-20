from setuptools import setup, find_packages

setup(
    name="suzuran-chain",
    version="0.1.0",
    packages=find_packages(),
    include_package_data=True,
    install_requires=[
        "fastapi>=0.109.0",
        "uvicorn>=0.27.0",
        "httpx>=0.26.0",
        "python-dotenv>=1.0.0",
        "pydantic>=2.0.0",
    ],
    python_requires=">=3.10",
    author="Suzuran Team",
    description="Minecraft AI Assistant Backend with MCP Support",
    keywords="minecraft, mcp, ai, assistant",
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
    ],
)
