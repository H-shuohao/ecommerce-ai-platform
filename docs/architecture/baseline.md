# 当前系统基线

## 现有请求链路

```text
用户语音
→ RTC 接收音频
→ ASR 转写文本
→ 后端 callback
→ RagService 检索并判断相关性
→ 将有效知识加入模型上下文
→ LLMService 流式生成回答
→ TTS 合成语音
→ RTC 返回用户
```

关键边界：LLM 不会主动检索知识库。应用代码先执行检索，再将检索结果作为上下文传给 LLM。

## 当前限制

- `main.py` 同时承担路由、数据模型和流程编排，职责过多。
- 模型和知识库实现与火山云绑定较深。
- RAG 只使用单个候选，缺少结构化引用与评测。
- `database.py` 尚未实现，没有持久化会话、检索和调用日志。
- Prompt 写在模型服务代码中，尚未实现版本管理。
- 尚未实现商品、库存和订单等 Agent 工具。
- `/health` 仅验证 FastAPI 存活，不检查外部依赖是否就绪。

## 2026-07-20 基线验证

- Python：3.13.13
- 依赖管理：uv 0.11.29
- `uv sync --locked`：通过
- `GET /health`：HTTP 200
- `GET /openapi.json`：HTTP 200
- 当前 OpenAPI 路由数量：7
- 当前 API 版本：1.0.0
- Git：当前终端未找到，需要安装或修复 PATH

本次验证只证明应用能够导入并正常响应基础路由；尚未验证依赖真实云端密钥的 LLM、RAG 和 RTC 链路。

## 下一阶段目标

在不改变现有行为的前提下拆分路由、Schema 和服务边界，并为模型供应商、Retriever、Prompt 和日志建立可替换接口。

## 第一轮分层重构

- 健康检查迁移至 `app/api/health.py`。
- 调试接口 Schema 迁移至 `app/schemas/debug.py`。
- `main.py` 使用 `include_router` 注册独立路由。
- 回归验证：健康检查 200、OpenAPI 路由仍为 7、非法空问题返回 422。
- 三个 AI 调试接口已迁移至 `app/api/debug.py`，旧实现已从 `main.py` 删除。
- 公共流式解析工具已迁移至 `app/core/streaming.py`。
- `main.py` 已缩减至约 326 行，当前剩余内容主要为 RTC 路由和应用组装。
- 自动化测试增加至 4 个，使用模拟 RAG/LLM 验证调用链，不消耗云端 Token。
- RTC 的 `/getScenes`、`/proxy`、`/api/chat_callback` 已全部迁移至 `app/api/rtc.py`。
- RTC Token 与必填配置工具位于 `app/core/rtc.py`。
- `main.py` 最终缩减为约 56 行，只负责应用创建、中间件、Router 注册和本地启动。
- 当前共有 7 个自动化测试，覆盖健康检查、RAG、调试聊天、RTC 场景、代理和语音回调。
- 已建立包含 4 个电商业务工具的 Tool Registry，并提供工具发现和统一调用 API。
- 自动化测试当前增加至 16 个。
- 2026-07-21 完成一次真实 RAG + LLM 验证：RAG 分数 0.3328，首 Token 约 2.364 秒，总耗时约 5.006 秒，总 Token 625。
- 已建立售前咨询 Agent 的 Planner、Tool Executor 和最终回答链路。
- 真实工具验证中，模型正确选择 `check_inventory(product_id="P1002")`；工具返回库存 0，最终答案正确，低分 RAG 候选被过滤。
- 自动化测试当前增加至 17 个。
- 售前 Agent 已升级为最多 3 轮工具执行，并加入相同工具与参数的重复调用保护。
- 商品搜索工具新增 `max_price`，并支持“油皮防晒”等组合关键词。
- 多工具真实验证成功：搜索 P1001（129 元）→ 查询库存 36 → 查询商品详情 → 生成推荐；无关 RAG 片段被过滤。
- 自动化测试当前增加至 20 个。
- 已加入 SQLite Agent 可观测性：`agent_runs` 与 `tool_calls` 表、Repository、运行列表和详情接口。
- 真实持久化验证成功：库存 Agent 运行耗时 5442 ms，问题、回答、工具轨迹和 RAG 状态均可按 UUID 读回。
- 自动化测试当前增加至 21 个。
