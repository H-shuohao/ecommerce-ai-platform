# Prometheus 与 Grafana 监控

## 这三个组件如何分工

- AI Core 负责处理业务请求，并在 `/metrics` 输出聚合指标。
- Prometheus 每 5 秒访问一次 `/metrics`，把每次采集到的数值保存为时间序列。
- Alertmanager 接收 Prometheus 告警，负责分组、去重、静默和路由。
- 本地 Webhook 收件箱接收 Alertmanager 转发的触发与恢复通知。
- Grafana 查询 Prometheus，并把请求速率、错误率、在途请求和延迟画成图表。

这相当于“业务服务负责报数，Prometheus 负责定时抄表和判断异常，Alertmanager 负责整理并派发异常消息，Grafana 负责把账本画成仪表盘”。

## 启动

在仓库根目录执行：

```powershell
docker compose up --build -d
docker compose ps
```

访问入口：

- AI Demo：<http://127.0.0.1:8000/demo>
- Prometheus：<http://127.0.0.1:9090>
- Alertmanager：<http://127.0.0.1:9093>
- 本地告警收件箱：<http://127.0.0.1:9087>
- Grafana：<http://127.0.0.1:3000>

Grafana 本地默认账号和密码均为 `admin`。首次登录后应立即修改密码。也可以在启动前设置：

```powershell
$env:GRAFANA_ADMIN_USER = "admin"
$env:GRAFANA_ADMIN_PASSWORD = "替换为本地强密码"
docker compose up --build -d
```

进入 Grafana 后，打开 **Dashboards → AI Platform → AI Core HTTP Overview**。

## 如何产生可观察数据

刚启动时图表数据很少是正常现象。打开 Demo 连续提问，或访问 Swagger、健康检查等接口，等待 5 到 10 秒后刷新仪表盘。

仪表盘包括：

- 请求速率：服务每秒收到多少请求；
- 服务端错误率：HTTP 5xx 请求所占比例；
- 正在处理的请求：当前尚未完成的并发请求；
- P95 延迟：95% 的近期请求都能在该时间以内完成；
- 状态码趋势：区分 2xx、4xx 和 5xx；
- 延迟趋势：对比 P50、P95 和 P99。
- 告警状态：显示当前正在触发的 AI Core 告警数量，`0` 表示正常。

## 自动告警规则

Prometheus 每 5 秒计算一次规则，当前包含：

| 告警 | 触发条件 | 等待时间 | 级别 |
|---|---|---:|---|
| `AIServiceDown` | 无法采集 AI Core 指标 | 30 秒 | critical |
| `AIHighServerErrorRate` | 最近两分钟 5xx 错误率持续超过 5% | 2 分钟 | warning |
| `AIHighP95Latency` | P95 延迟持续高于 5000 ms | 3 分钟 | warning |

等待时间的作用是过滤短暂网络抖动。例如一次请求偶尔超过 5 秒不会立刻报警，只有持续异常才会进入 `firing` 状态。

可以在 Prometheus 的 **Alerts** 页面查看规则状态：

<http://127.0.0.1:9090/alerts>

当前 Alertmanager 使用以下策略：

- 相同 `alertname` 和 `service` 的告警合并成一组；
- 首次等待 5 秒，避免同类告警在短时间内连续发送；
- 同组状态最短每 30 秒更新一次；
- 持续未恢复时每 4 小时提醒一次；
- 告警恢复后发送 `resolved` 通知。

本地 Webhook 收件箱会把通知保存到 Docker Volume，浏览器刷新
<http://127.0.0.1:9087> 即可查看。也可以使用
`GET http://127.0.0.1:9087/api/alerts` 获取 JSON。

真实生产环境可以把接收器替换为企业微信、钉钉、邮件或公司事件平台。当前本地收件箱用于证明通知路由真实可用，不代表生产通知渠道。

### 2026-07-26 本地故障演练

实际停止 `ai-core` 容器 38 秒后：

- `AIServiceDown` 进入 `firing` 状态；
- 重新启动容器后，`/health` 恢复为 `ok`；
- Prometheus 采集目标恢复为 `up`；
- 活动告警数量自动恢复为 `0`。
- Alertmanager 向本地 Webhook 分别发送了 `firing` 和 `resolved` 通知。

这证明当前规则不只是静态配置，而是能够真实发现服务中断并在恢复后自动解除。

## 安全边界

`/api/v1/metrics/http` 和 `/api/v1/metrics/alerts` 仍需要管理员权限。供 Prometheus 自动采集的 `/metrics` 不需要交互式登录，但只输出请求计数和延迟等聚合值，不包含请求正文、API Key、用户信息或业务数据。

生产部署时不应把 Prometheus 和 Grafana 端口直接暴露到公网，应通过内网、安全组或反向代理认证限制访问。当前 Compose 配置定位为本地演示与作品集验证。

Alertmanager 和本地告警收件箱也属于运维接口，生产部署时同样不能直接暴露到公网。

## 数据保留与重启

- Prometheus 数据默认保留 7 天，并保存在 `prometheus-data` Docker Volume 中。
- Grafana 配置和状态保存在 `grafana-data` Docker Volume 中。
- Alertmanager 状态保存在 `alertmanager-data`，本地通知记录保存在 `alert-webhook-data`。
- AI Core 当前指标注册表位于进程内，AI Core 重启后累计计数会从零开始；Prometheus 中已经采集的历史时间序列仍然保留。
- `docker compose down` 不会删除命名卷；只有显式执行 `docker compose down -v` 才会删除监控历史数据。
