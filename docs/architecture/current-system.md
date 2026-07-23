# 当前已实现系统架构

这张图只展示仓库中已经实现并验证的能力。直播切片和多模态素材中心按“基础版”展示；模型微调尚未实现，因此不画入已完成架构。

## 总体架构

```mermaid
flowchart TB
    subgraph clients["接入层"]
        Demo["售前对话 Demo"]
        Swagger["Swagger / REST Client"]
        RTC["RTC 语音 Agent"]
        MCPClient["Python / Cursor MCP Client"]
    end

    subgraph core["FastAPI AI Core"]
        API["API 路由层"]
        Presales["售前 Agent Loop"]
        Content["内容运营 Agent"]
        Eval["Agent 评测系统"]
        Observe["运行可观测性"]
        DataPlatform["轻量 AI 数据中台"]
        Assets["多模态素材中心（基础版）"]
        LiveClips["直播切片规划 Agent"]
        MCP["MCP Server"]
        Voice["RTC / ASR / TTS 回调"]
    end

    subgraph shared["共享业务与 AI 能力"]
        Registry["ToolRegistry"]
        Tools["商品 / 库存 / 订单工具"]
        RAG["火山知识库 RAG"]
        LLM["火山方舟 LLM"]
        Compliance["内容合规规则"]
    end

    subgraph data["数据与状态"]
        Commerce["commerce.json\n商品 / 库存 / 订单"]
        SQLite["SQLite\n会话 / Run / 审核 / 评测 / 发布"]
        Catalog["数据目录 / 质量报告 / 版本快照"]
    end

    Demo --> API
    Swagger --> API
    RTC --> Voice
    MCPClient --> MCP

    API --> Presales
    API --> Content
    API --> Eval
    API --> DataPlatform
    API --> Assets
    API --> LiveClips
    Voice --> RAG
    Voice --> LLM

    Presales --> Registry
    Presales --> RAG
    Presales --> LLM
    Content --> Registry
    Content --> LLM
    Content --> Compliance
    Eval --> Presales
    MCP --> Registry
    MCP --> DataPlatform

    Registry --> Tools
    Tools --> Commerce
    Presales --> SQLite
    Content --> SQLite
    Eval --> SQLite
    Observe --> SQLite
    DataPlatform --> Catalog
    DataPlatform --> Commerce
    DataPlatform --> SQLite
    Assets --> Commerce
    Assets --> SQLite
    LiveClips --> LLM
    LiveClips --> Assets
```

## 售前问题请求链路

以下链路以“请查询商品 P1002 是否有库存”为例。

```mermaid
sequenceDiagram
    actor User as 用户
    participant Client as Demo / API Client
    participant API as FastAPI
    participant Agent as Presales Agent Loop
    participant LLM as Planner LLM
    participant Registry as ToolRegistry
    participant Tool as check_inventory
    participant DB as 电商数据
    participant Log as SQLite

    User->>Client: 提问 P1002 是否有库存
    Client->>API: POST /api/v1/agents/presales/chat
    API->>Agent: question + session_id
    Agent->>LLM: 历史消息 + 工具说明 + 当前问题
    LLM-->>Agent: 选择 check_inventory(P1002)
    Agent->>Registry: 校验并调用工具
    Registry->>Tool: product_id=P1002
    Tool->>DB: 读取当前库存
    DB-->>Tool: quantity=0
    Tool-->>Agent: in_stock=false
    Agent->>LLM: 问题 + 可信工具结果
    LLM-->>Agent: 组织最终回答
    Agent->>Log: 保存会话、Run和工具调用
    Agent-->>API: answer + run_id + trace
    API-->>Client: JSON响应
    Client-->>User: 当前无库存
```

## 数据中台发布链路

```mermaid
flowchart LR
    Candidate["候选 commerce 数据"] --> Validate["Staging 校验"]
    Validate --> Rules["8项质量规则"]
    Rules --> Gate{"质量门禁通过?"}
    Gate -- "否" --> Blocked["blocked 版本\n不影响当前数据"]
    Gate -- "是" --> Published["published 版本"]
    Published --> Activate["激活版本"]
    Activate --> AgentData["Agent 使用的新快照"]
    History["历史 published 版本"] --> Rollback["回滚激活"]
    Rollback --> AgentData
```

## MCP 对外能力

```text
MCP Server (Streamable HTTP /mcp/)
├─ Tools
│  ├─ search_products
│  ├─ get_product
│  ├─ check_inventory
│  ├─ query_order
│  └─ search_media_assets
├─ Resources
│  └─ commerce://data-catalog
└─ Prompts
   └─ presales_assistant
```

## 如何讲这张图

面试时先讲主链路，不要逐个念技术名词：

> 用户通过网页、REST或语音入口访问 FastAPI。售前 Agent 使用大模型做工具规划，通过统一 ToolRegistry 查询商品、库存和订单，必要时结合 RAG，再由大模型组织回答。会话、工具调用、运行耗时和评测结果进入 SQLite。数据中台负责数据目录、质量校验、发布和回滚。相同业务工具还通过标准 MCP Server 提供给外部 Agent 客户端。服务最终使用 Docker Compose 进行标准化启动和健康检查。

然后根据面试官追问，再展开 Agent Loop、数据中台、MCP或评测模块。
