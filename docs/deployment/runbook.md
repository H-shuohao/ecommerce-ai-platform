# 部署与故障排查手册

本手册用于本地演示、面试展示和后续云服务器部署。真实密钥只保存在
`services/ai-core/.env` 或部署平台 Secret 中，不写入镜像、Git 和文档。

## 1. 启动前检查

在仓库根目录复制环境变量模板并填写真实配置：

```powershell
Copy-Item services\ai-core\.env.example services\ai-core\.env
```

本地模式检查：

```powershell
cd services\ai-core
.\.venv\Scripts\python.exe scripts\check_deployment_config.py
```

生产模式检查：

```powershell
.\.venv\Scripts\python.exe scripts\check_deployment_config.py --production
```

检查器只输出缺失或不安全的变量名，不输出变量值。生产模式要求：

- 大模型与 RAG 核心配置齐全；
- `API_AUTH_ENABLED=true`；
- viewer、service、admin 三个 API Key 均不少于16位且互不相同；
- 配置 RTC 公网回调时，`SERVER_URL` 必须使用 HTTPS。

## 2. Docker 标准启动

在仓库根目录执行：

```powershell
docker compose up --build -d
docker compose ps
```

预期容器 `ecommerce-ai-core` 状态最终变为 `healthy`。

访问入口：

- Demo：<http://127.0.0.1:8000/demo>
- Swagger：<http://127.0.0.1:8000/docs>
- 存活检查：<http://127.0.0.1:8000/health>
- 就绪检查：<http://127.0.0.1:8000/ready>

## 3. `/health` 与 `/ready` 的区别

`/health` 是存活检查，只证明 FastAPI 进程可以响应 HTTP。Docker
`HEALTHCHECK` 使用这个接口，避免因为临时外部服务故障反复重启容器。

`/ready` 是业务就绪检查，检查 LLM、RAG、RTC 所需配置是否存在：

- LLM 与 RAG 均配置时返回 HTTP 200；
- 核心配置缺失时返回 HTTP 503；
- RTC 未配置会单独显示 `false`，但不阻塞文字版 AI Core 启动。

当前 `/ready` 检查的是配置存在性，不代表火山引擎网络一定可达。真实外部
连通性由 Demo 请求、调试接口和日志进一步验证。

## 4. 日常操作

```powershell
# 查看容器状态
docker compose ps

# 持续查看日志
docker compose logs -f ai-core

# 重建并后台启动
docker compose up --build -d

# 停止并删除容器，保留本地 data 目录
docker compose down
```

不要同时运行 Cursor 中的 `main.py` 和 Docker 容器，否则两者会争用8000端口。

## 5. 常见故障排查

### 8000端口被占用

```powershell
Get-NetTCPConnection -LocalPort 8000
docker compose ps
```

关闭 Cursor 中旧的 Python 服务，或先执行 `docker compose down`。

### 容器启动但 Demo 无法回答

依次检查：

1. `GET /health` 是否为200；
2. `GET /ready` 中 `llm`、`rag` 是否为 `true`；
3. `docker compose logs -f ai-core` 是否出现外部模型或知识库报错；
4. `.env` 中配置名是否与 `.env.example` 一致；
5. 修改 `.env` 后是否重新创建容器。

### 修改代码后页面还是旧版本

Docker 镜像内的代码不会自动同步。执行：

```powershell
docker compose up --build -d
```

然后在浏览器使用 `Ctrl + Shift + R` 强制刷新。

### 接口返回401或403

- 401：缺少或使用了错误的 `X-API-Key`；
- 403：身份有效，但角色权限不足；
- 数据中台与评测管理使用 admin；
- Agent 与 MCP 执行使用 service 或 admin；
- 商品查询可使用 viewer、service 或 admin。

### 流式回答被一次性显示

确认响应头包含：

```text
Content-Type: application/x-ndjson
Cache-Control: no-cache, no-transform
X-Accel-Buffering: no
```

如果未来增加 Nginx，还需要关闭该路由的代理缓冲。Swagger 可能等待响应结束后
一次性展示，流式效果应在 `/demo` 或支持流式读取的客户端中验证。

### 模型请求超时或偶发网络错误

模型调用由以下环境变量控制：

```dotenv
LLM_TIMEOUT_SECONDS=30
LLM_MAX_ATTEMPTS=2
LLM_RETRY_BACKOFF_SECONDS=0.5
```

- `LLM_TIMEOUT_SECONDS`：单次模型请求最长等待时间；
- `LLM_MAX_ATTEMPTS`：包含首次调用在内的最多尝试次数；
- `LLM_RETRY_BACKOFF_SECONDS`：首次重试前的等待时间，后续按指数增加。

默认只尝试两次，避免外部服务持续故障时让请求长时间占用资源。流式回答已经向用户输出文字后不会从头重试，避免产生重复内容。

### 接口返回429

429表示当前客户端在时间窗口内用完了请求额度。响应头会返回：

```text
X-RateLimit-Limit: 60
X-RateLimit-Remaining: 0
X-RateLimit-Reset: 42
Retry-After: 42
```

本地开发默认关闭限流；生产配置检查要求启用：

```dotenv
RATE_LIMIT_ENABLED=true
RATE_LIMIT_REQUESTS=60
RATE_LIMIT_WINDOW_SECONDS=60
```

当前实现适合单进程作品集部署。多实例生产环境需要改用Redis等共享存储，否则每个进程会分别计算额度。

## 6. 数据持久化与备份

Compose 将 `services/ai-core/data` 映射到容器 `/app/data`，因此删除容器不会
删除本地 SQLite 和演示业务数据。备份前先停止写入，再复制整个 data 目录。

当前是单机作品集架构。若扩展为多实例部署，应将 SQLite、进程内缓存和本地
素材存储替换为 PostgreSQL、Redis 和对象存储。

## 7. 面试表达

可以这样概括：

> 我把存活检查与业务就绪检查分开：`/health` 只判断服务进程是否存活，
> `/ready` 判断模型和知识库配置是否具备。部署前还有独立配置检查器，
> 生产模式会强制认证开启并检查分角色密钥，且不会打印密钥内容。运行时通过
> Docker 健康检查、结构化日志和 request_id 排查问题，数据目录通过卷持久化。

## 8. 本地并发压测

服务启动后，在 `services/ai-core` 目录运行不调用大模型的基础压测：

```powershell
.\.venv\Scripts\python.exe scripts\load_test.py `
  --profile commerce `
  --requests 2000 `
  --concurrency 20 `
  --output ..\..\docs\performance\local-commerce.md
```

`agent`档位会真实调用Agent与大模型，可能产生费用，应该使用较小的请求数：

```powershell
.\.venv\Scripts\python.exe scripts\load_test.py `
  --profile agent `
  --requests 8 `
  --concurrency 2 `
  --timeout 90 `
  --output ..\..\docs\performance\local-agent.md
```

Agent 档位循环覆盖库存、订单、商品推荐和商品详情四类场景。成功条件不仅是 HTTP 2xx，还要求回答非空，并调用对应场景的预期工具。脚本会额外发送一次不计入报告的预热请求。

启用API认证时，在当前终端临时设置 `LOAD_TEST_API_KEY`，不要把真实密钥写进脚本或报告。压测结果只代表本次机器、网络、数据和服务配置，不能直接当作生产容量。

## 9. HTTP 指标监控

服务运行后，可先请求几次 `/health`、`/api/v1/products` 或 Agent 接口，再在 Swagger 的“系统监控”分组执行：

```text
GET /api/v1/metrics/http
```

该接口返回当前进程启动以来的 HTTP 请求总数、正在处理数、成功数、4xx/5xx 数量、各状态码和请求方法分布，以及平均耗时、P50、P95、P99。它适合开发调试和面试演示。

Prometheus 等监控系统可抓取：

```text
GET /metrics
```

该地址返回 Prometheus 文本格式，因此不以 Swagger JSON 的形式展示。启用 API 认证后，这两个监控出口都需要 `admin` 权限。

当前实现是单进程内存指标：服务重启后统计会清零，多 worker 或多容器之间也不会自动合并。生产环境应由 Prometheus 定时抓取每个实例，再用 Grafana 展示和配置告警，不能把当前数值直接当成整个集群的统计。

## 10. 指标告警判定

在 Swagger 的“系统监控”分组执行：

```text
GET /api/v1/metrics/alerts
```

响应中的 `status` 有三个等级：

- `healthy`：当前没有规则达到阈值；
- `warning`：需要关注，但未达到严重阈值；
- `critical`：P95、5xx错误率或正在处理的请求数达到严重阈值。

`evaluated=false` 表示当前样本数不足，系统暂不下结论，避免刚启动时一个慢请求造成误报警。默认至少累计20个请求才开始判定。阈值可通过以下环境变量调整：

```text
METRIC_ALERT_MINIMUM_SAMPLES=20
METRIC_ALERT_P95_WARNING_MS=3000
METRIC_ALERT_P95_CRITICAL_MS=5000
METRIC_ALERT_ERROR_RATE_WARNING_PERCENT=1
METRIC_ALERT_ERROR_RATE_CRITICAL_PERCENT=5
METRIC_ALERT_IN_FLIGHT_WARNING=20
METRIC_ALERT_IN_FLIGHT_CRITICAL=50
```

当前功能负责“发现并描述异常”，没有主动发送邮件、微信或钉钉消息。生产环境通常由 Prometheus Alertmanager 或云监控读取指标后负责通知、静默和升级。

## 11. JWT 用户登录

系统保留两种认证方式：

- API Key：适合后端服务、MCP客户端和自动化脚本；
- Bearer JWT：适合用户登录后访问HTTP接口。

JWT默认关闭。先在 `services/ai-core` 目录运行密码哈希生成器，输入过程不会显示密码：

```powershell
.\.venv\Scripts\python.exe scripts\generate_password_hash.py
```

再生成至少32位的随机签名密钥：

```powershell
.\.venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(48))"
```

把输出填写到本地 `.env`，不要提交真实值。`AUTH_USERS_JSON` 只作为兼容或首次启动账号来源，可以暂时保持空数组：

```text
API_AUTH_ENABLED=true
JWT_AUTH_ENABLED=true
JWT_SECRET=这里填写随机签名密钥
JWT_ISSUER=ecommerce-ai-platform
JWT_EXPIRES_MINUTES=60
AUTH_USERS_JSON=[]
```

重新启动服务后，先使用 admin API Key 在 Swagger 创建数据库账号：

```text
POST /api/v1/auth/users
```

示例请求体：

```json
{
  "username": "demo-viewer",
  "password": "请填写至少8位的测试密码",
  "role": "viewer"
}
```

这里传入的是原始密码，但后端写入 SQLite 前会转换为 PBKDF2 哈希；接口响应和用户列表都不会返回密码或密码哈希。首个数据库账号也可以暂时通过 `AUTH_USERS_JSON` 启动账号登录，但后续账号建议统一由管理接口创建。

创建账号后调用：

```text
POST /api/v1/auth/login
```

请求体填写用户名和原始密码。成功响应中的 `access_token` 是短期JWT，不是密码哈希。点击 Swagger 右上角 `Authorize`，选择 `BearerAuth` 并填写该 Token，即可按用户角色访问接口。

JWT包含用户名、角色、签发方和过期时间，但不包含密码。后端会验证HS256签名、签发方和过期时间。viewer Token可以读取商品，不能访问数据中台和监控管理接口；service可执行Agent；admin拥有平台管理权限。

管理员还可以调用以下接口：

```text
GET /api/v1/auth/users
GET /api/v1/auth/login-audits
```

第一个接口用于查看数据库账号、角色和启用状态，第二个接口用于查看登录是否成功、失败原因、来源IP和时间。登录时优先读取数据库账号，找不到时才兼容读取 `AUTH_USERS_JSON`。

当前已完成数据库用户表、密码哈希、角色权限和登录审计，仍未实现刷新Token、注销黑名单、账号停用接口、密码重置和多因素认证。生产系统应继续补充这些能力。
