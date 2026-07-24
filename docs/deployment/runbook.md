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
