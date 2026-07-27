# 内容运营 Agent：持久化异步任务

## 为什么需要异步任务

内容生成需要调用外部大模型，通常要等待数秒。如果 HTTP 请求一直阻塞，用户容易重复点击，网关也可能超时。异步接口把“提交任务”和“取得结果”拆开：

```text
客户端提交任务
  ↓ 立即返回 202 + job_id
SQLite 保存 queued 状态
  ↓
进程内 Worker 调用内容生成服务
  ↓
成功：保存草稿并标记 succeeded
失败：记录错误并标记 failed
  ↓
客户端按 job_id 查询状态
```

## 已实现能力

- `POST /api/v1/agents/content/jobs`：提交内容生成任务，立即返回 `202 Accepted`。
- `GET /api/v1/agents/content/jobs/{job_id}`：查询单个任务状态。
- `GET /api/v1/agents/content/jobs`：按状态分页查询任务。
- `POST /api/v1/agents/content/jobs/{job_id}/retry`：在最大次数内重试失败任务。
- `X-Idempotency-Key`：同一个业务请求重复提交时复用原任务，避免重复生成和重复计费。
- SQLite 持久化：保存任务参数、状态、重试次数、错误、草稿编号和时间戳。
- 重启恢复：进程退出时被中断的 `running` 任务会在下次启动时重新进入 `queued` 并恢复执行。

任务状态流转：

```text
queued → running → succeeded
                  ↘ failed → queued（人工重试）
```

成功任务会关联一个内容草稿 `draft_id`。草稿仍需经过合规检查和人工审核，批准后才进入多模态素材中心。

## Swagger 验证顺序

1. 调用 `POST /api/v1/agents/content/jobs`，请求头可填写唯一的 `X-Idempotency-Key`。
2. 复制响应中的 `id`。
3. 调用 `GET /api/v1/agents/content/jobs/{job_id}`，观察 `queued → running → succeeded`。
4. 成功后复制 `draft_id`，再查询草稿、执行合规检查和人工审核。
5. 使用相同幂等键再次提交，验证返回相同任务编号。

## 当前工程边界

这是适合个人作品集和单实例服务的可靠异步方案，但不是分布式任务平台：

- Worker 与 API 运行在同一 Python 进程；
- SQLite 适合当前数据量和单机演示；
- 暂未实现多实例抢占、任务租约、死信队列和独立 Worker 扩缩容。

如果进入多实例生产环境，可将任务存储和调度迁移到 Redis/Celery、RQ 或云任务队列；业务 API、状态机、幂等语义和草稿审核流程可以继续复用。

## 面试表达

> 内容生成依赖外部模型，早期同步接口会让请求阻塞数秒，也容易因用户重复点击产生重复调用。我把生成流程改成了持久化异步任务：接口先返回 202 和任务编号，后台 Worker 执行模型调用，SQLite 记录状态和错误；通过幂等键避免重复任务，并支持失败重试和服务重启恢复。当前是单实例轻量方案，同时明确保留了迁移到 Redis/Celery 的边界。
