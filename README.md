# 电商生态 AI Agent 平台

[![AI Core Tests](https://github.com/H-shuohao/ecommerce-ai-platform/actions/workflows/ai-core-tests.yml/badge.svg)](https://github.com/H-shuohao/ecommerce-ai-platform/actions/workflows/ai-core-tests.yml)

面向应届生求职展示的个人 AI 工程项目。项目以模拟电商商品、库存和订单数据为业务基础，将大模型、RAG、Agent Loop、MCP、数据治理、评测与可观测能力组合成一套可以真实运行和验证的轻量平台。

> 项目定位：个人作品集与工程实践，不宣称为真实企业生产系统。

## 已实现能力

- **售前咨询 Agent**：大模型规划工具调用，支持商品搜索、商品详情、实时库存和订单查询。
- **多轮会话记忆**：使用 SQLite 保存会话，前端自动管理 `session_id`，动态库存问题强制刷新。
- **RAG 与大模型**：接入火山引擎知识库和模型服务，支持相关性过滤与调试接口。
- **内容运营 Agent**：生成多平台商品文案，支持草稿、编辑、人工审核和高风险内容拦截。
- **多模态素材中心（基础版）**：统一登记图片、视频和文本素材元数据，支持商品、类型和标签检索。
- **直播切片 Agent（基础版）**：根据带时间戳转写识别直播高光，校验时间范围并沉淀视频切片计划。
- **轻量数据中台**：数据资产目录、8项质量规则、候选数据校验、发布门禁、版本激活和回滚。
- **Agent 评测系统**：固定测试集、工具选择准确率、耗时、历史版本与基线对比。
- **运行可观测性**：记录 Agent 运行、工具调用、成功率、耗时和 RAG 使用情况。
- **标准 MCP Server**：通过 Streamable HTTP 暴露5个 Tools、1个 Resource和1个 Prompt。
- **RTC 语音链路**：保留原项目 RTC、ASR、LLM/RAG、TTS 回调能力。
- **容器化交付**：Dockerfile、Docker Compose、健康检查、端口映射和 SQLite 数据持久化。
- **持续集成**：GitHub Actions 在独立 Python 3.13 环境中自动运行测试。

## 架构概览

详细架构图与请求链路见：[当前已实现系统架构](docs/architecture/current-system.md)。原始8项目规划与真实完成度见：[八项目进度矩阵](docs/architecture/eight-project-roadmap.md)。

第一次查看项目可按[五分钟稳定演示路线](docs/demo/five-minute-walkthrough.md)，从售前 Agent、多轮记忆、运行追踪一路演示到数据中台和 GitHub Actions。

求职介绍与技术边界见[正式项目介绍与背诵提纲](docs/interview/30-formal-project-introduction.md)。

```text
浏览器 / RTC Agent / MCP Client
              │
        FastAPI AI Core
              │
   ┌──────────┼───────────┐
   │          │           │
Agent Loop  Data Platform  MCP Server
   │          │           │
ToolRegistry 质量/发布/回滚 Tools/Resource/Prompt
   │
商品 / 库存 / 订单 / RAG / LLM
              │
     SQLite 运行与评测数据
```

## 真实验证结果

- 自动化测试：`55/55` 通过。
- 售前 Agent 基线评测：`4/4` 通过。
- 工具选择准确率：`100%`。
- 基线平均耗时：`6368.75 ms`（真实模型调用环境，结果会随网络与模型状态变化）。
- Docker 容器健康状态：`healthy`，`/health` 与 `/docs` 均返回 HTTP 200。

## 目录结构

```text
ecommerce-ai-platform/
├─ .cursor/                 # Cursor 项目级 MCP 配置
├─ docs/
│  ├─ architecture/         # 架构与技术决策
│  ├─ evaluation/           # 真实评测记录
│  └─ interview/            # 面试复习与真实问题案例
├─ services/
│  └─ ai-core/
│     ├─ app/               # API、Schema、Repository、Tools、MCP
│     ├─ services/          # Agent、RAG、数据中台、评测等业务服务
│     ├─ data/              # 演示业务数据与 SQLite 数据
│     ├─ tests/             # 自动化测试
│     ├─ web/               # 售前对话演示页面
│     └─ Dockerfile
├─ docker-compose.yml
└─ README.md
```

## 本地开发启动

```powershell
cd services\ai-core
uv sync --locked
uv run uvicorn main:app --reload --port 8000
```

也可以使用项目现有虚拟环境：

```powershell
cd services\ai-core
.\.venv\Scripts\python.exe main.py
```

## Docker 启动

在仓库根目录执行：

```powershell
docker compose up --build -d
docker compose ps
```

查看日志和停止服务：

```powershell
docker compose logs -f ai-core
docker compose down
```

开发模式与 Docker 模式不要同时启动，否则都会占用8000端口。

## 访问入口

- 对话演示：<http://127.0.0.1:8000/demo>
- Swagger：<http://127.0.0.1:8000/docs>
- 健康检查：<http://127.0.0.1:8000/health>
- MCP Streamable HTTP：`http://127.0.0.1:8000/mcp/`

## MCP 本地验证

保持后端运行，在第二个终端执行：

```powershell
cd services\ai-core
.\.venv\Scripts\python.exe scripts\test_mcp_client.py
```

客户端将完成 MCP 初始化、5个工具发现、数据目录资源读取、售前 Prompt 获取和库存工具调用。

## 自动化测试

测试必须从 `services/ai-core` 目录运行：

```powershell
cd services\ai-core
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

同一测试命令已配置在 `.github/workflows/ai-core-tests.yml`。推送到 GitHub 后，会在 `main` 分支的 push 和 pull request 上自动运行。

## 环境变量与安全

1. 复制 `services/ai-core/.env.example` 为 `.env`。
2. 只在本地 `.env` 中填写真实密钥。
3. `.env` 已被 Git 和 Docker 构建上下文排除。
4. Docker Compose 在容器启动时注入环境变量，不把密钥写入镜像。

未配置外部模型、知识库或 RTC 凭据时，部分真实外部能力不可用，但本地商品、库存、订单、数据中台、评测和基础 API 仍可运行。

## 当前边界与后续路线

当前重点完成了 AI Core、售前 Agent、内容 Agent、轻量数据中台、评测、MCP、素材中心基础版、直播切片规划基础版和容器化闭环。FFmpeg物理裁剪、真实对象存储、生成式图片/视频和模型微调仍属于后续路线，不在当前简历中描述为已完成能力。

所有简历指标必须来自真实测试或运行记录，不虚构并发量、准确率、用户规模和商业收益。
