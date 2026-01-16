# MCP 接口测试智能体应用

> 基于 MCP 协议的智能化接口测试自动化解决方案

## 📋 项目概述

本项目为百万行代码级别的信贷系统重构工程（5000+ 接口）提供智能化接口测试解决方案。采用 **MCP-aware Agent + 独立 MCP Server** 的分层架构，实现接口文档解析、测试用例自动生成、测试执行和报告分析的全流程自动化。

## ✨ 核心特性

### 🎯 智能化测试
- **AI 驱动测试用例生成**：集成 Dify API，基于接口文档自动生成测试用例
- **上下文增强**：向量知识库 + 长短期记忆，突破 Dify 20k token 限制
- **语义检索**：相似接口智能关联，提升测试覆盖率

### 🔄 断点续传机制
- **检查点保存**：任务执行过程实时保存状态
- **智能恢复**：失败后从中断点继续执行
- **状态机管理**：8 种状态精确控制任务生命周期

### 🚀 高性能执行
- **双引擎支持**：Requests（轻量）+ HttpRunner（高级）
- **并发执行**：线程池管理，5倍速度提升
- **实时推送**：WebSocket 实时监控测试进度

### 📊 丰富报告
- **双格式导出**：Markdown + HTML（带样式）
- **详细统计**：通过率、耗时分析、错误模式识别
- **可视化图表**：进度条、Top 10 最慢用例

## 🏗️ 技术架构

```
┌─────────────────────────────────────────────────────────┐
│                    用户界面层                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │   Vue 前端   │  │  命令行工具  │  │  RESTful API │  │
│  └──────────────┘  └──────────────┘  └──────────────┘  │
└───────────────────────┬─────────────────────────────────┘
                        │
┌───────────────────────▼─────────────────────────────────┐
│                  Agent 核心层                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │  任务管理器  │  │ 工作流编排器 │  │  MCP 客户端  │  │
│  └──────────────┘  └──────────────┘  └──────────────┘  │
│  ┌──────────────┐  ┌──────────────┐                    │
│  │  记忆管理器  │  │ Agent 服务   │                    │
│  └──────────────┘  └──────────────┘                    │
└───────────────────────┬─────────────────────────────────┘
                        │
┌───────────────────────▼─────────────────────────────────┐
│                  MCP Server 层                           │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │ 文档解析器   │  │ 用例生成器   │  │  测试执行器  │  │
│  └──────────────┘  └──────────────┘  └──────────────┘  │
└───────────────────────┬─────────────────────────────────┘
                        │
┌───────────────────────▼─────────────────────────────────┐
│                  基础设施层                               │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │  配置管理    │  │   日志系统   │  │    数据库    │  │
│  └──────────────┘  └──────────────┘  └──────────────┘  │
│  ┌──────────────┐  ┌──────────────┐                    │
│  │ 文件存储     │  │ 向量数据库   │                    │
│  └──────────────┘  └──────────────┘                    │
└─────────────────────────────────────────────────────────┘
```

## 📦 技术栈

### 后端
- **语言**：Python 3.12
- **框架**：FastAPI, AgentScope
- **数据库**：SQLite（任务管理）、ChromaDB/Faiss（向量检索）
- **测试引擎**：Requests, HttpRunner
- **配置**：TOML

### 前端
- **框架**：Vue 3.5.26
- **运行时**：Node.js 24.11.1
- **构建工具**：Vite

### AI 集成
- **LLM API**：Dify 工作流 API
- **嵌入模型**：sentence-transformers

## 🚀 快速开始

### 1. 环境要求

- Python 3.12+
- Node.js 18+
- 8GB+ 内存

### 2. 安装依赖

```bash
# 后端依赖
pip install -r requirements.txt

# 前端依赖（待实现）
cd frontend
npm install
```

### 3. 配置文件

复制配置模板并修改：

```bash
cd config
cp default.toml.example default.toml
cp dify.toml.example dify.toml
# ... 根据实际情况修改配置
```

**关键配置项**：
- `config/dify.toml`：Dify API 密钥和工作流 ID
- `config/vectordb.toml`：向量数据库路径
- `config/testengine.toml`：测试引擎选择

### 4. 启动服务

```bash
# 启动后端服务
python backend/main.py

# 启动前端（待实现）
cd frontend
npm run dev
```

服务地址：
- API 服务：http://localhost:8000
- API 文档：http://localhost:8000/docs
- 前端界面：http://localhost:3000（待实现）

## 📖 使用指南

### 方式一：Web 界面（推荐）

1. 访问 http://localhost:3000
2. 上传接口文档（OpenAPI/Swagger/JSON）
3. 点击"开始测试"
4. 实时查看进度
5. 下载测试报告

### 方式二：命令行

```bash
# 创建任务
mcp-test create --doc path/to/swagger.json

# 查看任务状态
mcp-test status <task_id>

# 下载报告
mcp-test report <task_id> --format html
```

### 方式三：API 调用

```python
import requests

# 创建任务
response = requests.post("http://localhost:8000/api/tasks", json={
    "task_type": "api_test",
    "document_path": "/path/to/swagger.json",
    "config": {
        "test_engine": "requests",
        "parallel_execution": True
    }
})

task_id = response.json()["task_id"]

# 查询进度
status = requests.get(f"http://localhost:8000/api/tasks/{task_id}")
print(status.json())
```

## 📂 项目结构

```
mcp-autotest/
├── backend/                    # 后端代码
│   ├── agent/                 # Agent 核心
│   │   ├── task_manager.py   # 任务管理器
│   │   ├── workflow_orchestrator.py  # 工作流编排
│   │   ├── mcp_client.py     # MCP 客户端
│   │   └── agent_service.py  # HTTP 服务
│   ├── common/                # 通用模块
│   │   ├── config.py         # 配置管理
│   │   ├── logger.py         # 日志系统
│   │   ├── database.py       # 数据库
│   │   ├── storage.py        # 文件存储
│   │   ├── vectordb.py       # 向量数据库
│   │   ├── memory.py         # 记忆管理
│   │   ├── test_models.py    # 测试数据模型
│   │   ├── report_generator.py  # 报告生成器
│   │   ├── dify_client.py    # Dify 客户端
│   │   └── engines/          # 测试引擎
│   │       ├── requests_engine.py
│   │       └── httprunner_engine.py
│   ├── mcp_servers/           # MCP Servers
│   │   ├── base.py           # 基类
│   │   ├── doc_parser.py     # 文档解析
│   │   ├── testcase_generator.py  # 用例生成
│   │   └── test_executor.py  # 测试执行
│   └── main.py               # 主入口
├── frontend/                  # 前端代码（待实现）
├── config/                    # 配置文件
├── scripts/                   # 脚本
├── docs/                      # 文档
├── data/                      # 数据目录
├── requirements.txt           # Python 依赖
└── README.md                  # 本文件
```

## 🎯 开发进度

### ✅ 已完成（约 60%）

- [x] **第一阶段**：核心架构搭建（100%）
- [x] **第二阶段**：测试用例生成功能（100%）
- [x] **第三阶段**：自动化测试执行功能（100%）
- [x] **第四阶段**：Agent 核心实现（100%）

### ⏳ 进行中

- [ ] **第五阶段**：前端界面开发（0%）
- [ ] **第六阶段**：命令行工具开发（0%）
- [ ] **第七阶段**：内网移植准备（0%）
- [ ] **第八阶段**：集成测试与优化（0%）

## 🔧 配置说明

### 断点续传配置

断点续传机制自动启用，无需额外配置。任务执行过程中，系统会自动：
1. 每完成一个步骤保存检查点
2. 记录当前状态和上下文数据
3. 失败后调用 `/api/tasks/{task_id}/retry` 自动恢复

### 日志级别说明

⚠️ **用户特别偏好**：日志级别关系为 `DEBUG < INFO < WARNING < ERROR < CRITICAL`

```toml
# config/default.toml
log_level = "INFO"  # 推荐生产环境
# log_level = "DEBUG"  # 开发调试时使用
```

### 向量数据库配置

支持 ChromaDB（推荐）和 Faiss：

```toml
# config/vectordb.toml
backend = "chromadb"  # 或 "faiss"
persist_directory = "data/vectordb"
collection_name = "interface_knowledge"
embedding_model = "paraphrase-multilingual-MiniLM-L12-v2"
```

## 📝 API 文档

完整 API 文档访问：http://localhost:8000/docs

### 主要端点

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/tasks` | 创建新任务 |
| GET | `/api/tasks/{task_id}` | 获取任务详情 |
| GET | `/api/tasks` | 列出任务列表 |
| POST | `/api/tasks/{task_id}/retry` | 重试失败任务 |
| POST | `/api/tasks/{task_id}/cancel` | 取消任务 |
| GET | `/api/statistics` | 获取统计信息 |
| POST | `/api/upload` | 上传文档 |
| GET | `/api/reports/{task_id}` | 下载报告 |
| WS | `/ws` | WebSocket 实时推送 |

## 🤝 贡献指南

欢迎贡献代码、报告问题或提出建议！

1. Fork 本仓库
2. 创建特性分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 开启 Pull Request

## 📄 许可证

MIT License

## 👥 联系方式

- 项目地址：https://github.com/GUODnuli/mcp-autotest
- 问题反馈：https://github.com/GUODnuli/mcp-autotest/issues

## 🙏 致谢

- [AgentScope](https://github.com/modelscope/agentscope) - 多智能体框架
- [Dify](https://dify.ai/) - LLM 应用开发平台
- [ChromaDB](https://www.trychroma.com/) - 向量数据库
- [HttpRunner](https://httprunner.com/) - HTTP 测试框架
