# 02_quick_start - 快速开始示例

## 概述

本示例展示如何使用 Suzuran-Chain 脚手架快速构建一个完整的 MVP 应用，并注册 WikiRAG 功能。

## 功能特性

- ✅ 基于 MCP 脚手架的最小可行产品
- ✅ 内置 LLM 角色（Agent）
- ✅ 内置 MCP 客户端接口
- ✅ 注册 WikiRAG 实现 Minecraft Wiki 知识检索
- ✅ 完整的权限配置

## 架构说明

```
┌─────────────────────────────────────────────────┐
│                   客户端请求                      │
└─────────────────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────┐
│          MCP Scaffold（脚手架）                   │
│  ┌────────────────┐  ┌──────────────────────┐   │
│  │  agent:default │  │  mcp:client          │   │
│  │  - LLM 调用    │  │  - 客户端接口        │   │
│  └────────────────┘  └──────────────────────┘   │
│                        │                        │
│                        ▼                        │
│  ┌──────────────────────────────────────────┐   │
│  │  rag:wiki（通过 register_builtin 注册）   │   │
│  │  - Minecraft Wiki 检索                    │   │
│  └──────────────────────────────────────────┘   │
└─────────────────────────────────────────────────┘
```

## 快速开始

### 1. 安装依赖

```bash
cd suzuran-chain
pip install -r requirements.txt
```

### 2. 配置环境变量

复制 `.env.example` 为 `.env` 并修改配置：

```bash
cd example/02_quick_start
cp .env.example .env
```

编辑 `.env` 文件：

```env
OPENAI_API_BASE=https://api.your-provider.com/v1
OPENAI_API_KEY=your_actual_api_key
MODEL_NAME=gpt-4o-mini
```

### 3. 运行服务

```bash
python main.py
```

启动日志示例：

```
============================================================
搭建 MCP 脚手架...
============================================================
✅ 注册 LLM: agent:default-agent
✅ 注册 MCP 客户端: mcp:client
✅ 配置默认权限
✅ 注册 Agent 消息处理器
✅ 注册 Prompt
============================================================
MCP 脚手架搭建完成
============================================================
✅ 已注册 WikiRAG: rag:wiki
✅ 已配置权限
当前角色: ['agent:default-agent', 'mcp:client', 'rag:wiki']
```

### 4. 测试

#### 测试基础对话

```bash
curl -X POST http://localhost:8000/api/message -H "Content-Type: application/json" -d '{"message":"你好"}'
```

#### 测试 Wiki 检索

```bash
curl -X POST http://localhost:8000/api/message -H "Content-Type: application/json" -d '{"message":"帮我查一下铃兰的信息"}'
```

#### 查看服务状态

```bash
curl http://localhost:8000/
```

响应示例：

```json
{
  "service": "Quick Start Example",
  "version": "1.0.0",
  "status": "running",
  "registered_roles": ["agent:default-agent", "mcp:client", "rag:wiki"],
  "builtin_roles": ["rag:wiki"],
  "endpoints": {
    "message": "/api/message",
    "docs": "/docs",
    "roles": "/api/roles",
    "permissions": "/api/permissions"
  }
}
```

## 代码结构

```
02_quick_start/
├── main.py          # 主应用入口
├── .env.example     # 环境变量示例
└── README.md        # 说明文档
```

### main.py 核心代码说明

1. **创建脚手架**：

```python
llm_config = LLMConfig.from_env()
scaffold = create_mcp_scaffold(llm_config)
```

2. **注册内置功能**：

```python
wiki_rag = WikiRAG()
rag_id = scaffold.register_builtin(wiki_rag)
```

3. **配置权限**：

```python
server.grant_permission(rag_id, "agent:default-agent", ["execute"])
```

## 扩展说明

### 注册更多内置功能

```python
from suzuran_chain.rag.wiki import WikiRAG
from suzuran_chain.tool.echo import EchoTool

scaffold.register_builtin(WikiRAG())
scaffold.register_builtin(EchoTool())
```

### 注册自定义功能

```python
from suzuran_chain.mcp.protocol import Role, Adapter

class MyCustomRole(Role):
    def __init__(self):
        adapter = MyAdapter(self)
        super().__init__(adapter)
    
    def get_role_id(self):
        return "custom:my-role"
    
    def get_role_type(self):
        return "custom"
    
    # ... 其他方法

scaffold.register_custom(MyCustomRole())
```

## 可用 API 端点

| 端点 | 方法 | 说明 |
|------|------|------|
| `/` | GET | 服务状态 |
| `/api/message` | POST | 消息处理 |
| `/api/roles` | GET | 角色列表 |
| `/api/permissions` | GET | 权限列表 |
| `/docs` | GET | API 文档 |

## 参考文档

- [Suzuran-Chain 架构文档](../../docs/architecture.md)
- [MCP 脚手架使用指南](../../docs/scaffold.md)
- [WikiRAG 模块](../../suzuran_chain/rag/wiki.py)
