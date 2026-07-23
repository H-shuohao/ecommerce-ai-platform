# 五分钟稳定演示路线

这份路线用于录屏、作品展示和面试现场演示。目标不是把所有接口点一遍，而是用一条业务故事证明平台的核心闭环。

## 演示前准备

1. 启动 Docker Desktop，确认左下角显示 `Engine running`。
2. 在项目根目录执行：

   ```powershell
   docker compose up -d
   ```

3. 打开以下页面：

   - 售前对话：<http://127.0.0.1:8000/demo>
   - API 文档：<http://127.0.0.1:8000/docs>
   - 健康检查：<http://127.0.0.1:8000/health>

4. 如果真实 LLM 或 RAG 服务不可用，不要假装成功。先说明外部模型依赖当前不可用，再展示不依赖模型的健康检查、数据中台、工具与历史运行记录。

## 第1分钟：证明服务可运行

打开 `/health`，确认返回：

```json
{
  "status": "ok",
  "service": "xiaolan-ai-project-assistant",
  "docs": "/docs"
}
```

讲解：

> 项目使用 FastAPI 提供统一服务入口，并通过 Docker Compose 标准化启动。健康检查可以被 Docker 或部署平台用来判断服务是否存活。

## 第2分钟：演示售前 Agent 主链路

打开 `/demo`，依次发送：

1. `请推荐一款适合油皮的商品`
2. `那它现在有库存吗？`

观察：

- 第一轮由 Agent 选择 `search_products`；
- Agent 可继续选择 `check_inventory`；
- 第二轮不必重复商品编号；
- 页面自动保存 `session_id`，用户不需要手工复制；
- 回答下方可以看到工具调用和运行信息。

讲解：

> 大模型不是直接猜商品信息，而是负责规划工具。商品、价格和库存来自业务工具；会话历史保存在 SQLite，因此第二轮可以理解“它”指的是上一轮商品。

## 第3分钟：证明答案可追踪

在 Swagger 中打开：

1. `GET /api/v1/agents/runs`
2. 复制刚才一次运行的 `run_id`
3. 打开 `GET /api/v1/agents/runs/{run_id}`
4. 打开 `GET /api/v1/agents/runs/metrics`

观察：

- 问题与最终回答；
- 工具名称、参数和返回结果；
- 运行状态与耗时；
- 成功率和工具使用统计。

讲解：

> Agent 不是黑盒。每次运行都会记录问题、工具轨迹、耗时、RAG使用情况和异常，便于排错、统计和评测。

## 第4分钟：演示可信数据和内容闭环

先打开：

1. `GET /api/v1/data-platform/catalog`
2. `GET /api/v1/data-platform/quality/commerce`

然后说明数据发布流程：

```text
候选数据 → Staging校验 → 质量门禁 → 发布版本 → 激活/回滚 → Agent使用
```

如时间允许，再演示：

1. `POST /api/v1/agents/content/generate`
2. `GET /api/v1/agents/content/drafts/{draft_id}/compliance`
3. `POST /api/v1/agents/content/drafts/{draft_id}/review`
4. `GET /api/v1/assets`

讲解：

> 数据中台保证 Agent 使用的数据经过质量检查和版本管理。内容 Agent 生成的文案必须经过合规检查和人工审批，批准后才会沉淀到素材中心。

## 第5分钟：证明工程质量

打开 GitHub 仓库：

<https://github.com/H-shuohao/ecommerce-ai-platform>

展示：

- README 架构说明；
- `AI Core Tests` 绿色徽章；
- GitHub Actions 自动测试记录；
- `tests`、`Dockerfile`、`docker-compose.yml`；
- `docs/interview` 中的学习与问题复盘。

讲解：

> 项目包含54项本地自动化测试，并配置 GitHub Actions。每次推送到 main 分支后，GitHub 会在独立 Python 3.13 环境中重新安装依赖并运行测试，避免项目只能在我的电脑上运行。

## 面试现场的取舍

如果面试官只给2分钟，只展示：

1. `/demo` 两轮对话；
2. 一次 Agent Run 工具轨迹；
3. GitHub Actions 绿色记录。

如果面试官继续深挖，再按兴趣展开：

- Agent Loop：为什么要限制循环次数，如何处理未知工具；
- RAG：什么时候检索知识库，如何减少无关上下文；
- 数据中台：质量门禁、版本激活和回滚；
- MCP：如何把同一批工具提供给外部 Agent 客户端；
- 评测：固定用例、工具选择准确率和基线比较。

## 不能演示成已完成的部分

- 直播模块目前生成高光切片计划，尚未使用 FFmpeg 物理裁剪视频；
- 素材中心目前管理元数据和 URI，尚未接入对象存储上传文件；
- 项目没有完成 SFT/DPO 模型微调；
- 演示数据是模拟电商数据，不代表真实企业业务规模。
