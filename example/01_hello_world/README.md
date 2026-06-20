# 01_hello_world - Hello World 示例

## 概述

本示例展示如何使用 Suzuran-Chain 架构构建一个最简单的后端应用：对于任何客户端请求，均返回 "Hello world!"。

## 架构说明

本示例使用了 Suzuran-Chain 的核心组件：

1. **Role（角色）**：`HelloWorldRole` - 定义业务逻辑
2. **Adapter（适配器）**：`HelloWorldAdapter` - 处理协议转换
3. **MCPMessage（消息）**：消息载体

### 核心流程

```
客户端请求
    ↓
Adapter.unwrap_mcp() → 解析消息
    ↓
Role.handle() → 处理业务逻辑
    ↓
Adapter.wrap_mcp() → 封装响应
    ↓
返回客户端
```

## 快速开始

### 1. 安装依赖

```bash
cd suzuran-chain
pip install -r requirements.txt
```

### 2. 运行服务

```bash
cd example/01_hello_world
python main.py
```

### 3. 测试

使用 curl 或浏览器测试：

```bash
# 测试消息接口
curl -X POST http://localhost:8000/api/message -H "Content-Type: application/json" -d '{"message":"任何内容"}'

# 响应
{"response": "Hello world!"}
```

访问 http://localhost:8000 查看服务状态。

## 代码结构

```
01_hello_world/
├── main.py          # 主应用入口
└── README.md        # 说明文档
```

### main.py 核心代码说明

1. **HelloWorldAdapter**：适配器类
   - `wrap_mcp()`：将业务结果封装为 MCPMessage
   - `unwrap_mcp()`：从 MCPMessage 解析业务数据

2. **HelloWorldRole**：角色类
   - 继承自 `Role` 基类
   - 强制持有 `Adapter` 实例
   - `handle()` 方法实现业务逻辑（返回 "Hello world!"）

3. **API 端点**：
   - `POST /api/message`：接收消息，返回响应
   - `GET /`：服务状态

## 扩展说明

要扩展此示例，只需：

1. 创建新的 `Role` 子类
2. 实现 `handle()` 方法添加业务逻辑
3. 在 API 端点中使用新角色

## 参考文档

- [Suzuran-Chain 架构文档](../../docs/architecture.md)
- [Role 和 Adapter 设计模式](../../docs/role_adapter.md)
