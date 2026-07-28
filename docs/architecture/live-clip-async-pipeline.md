# 直播切片持久化异步流水线

## 为什么需要异步任务

一次直播回放处理可能包含大模型选段、FFprobe读取时长和多个FFmpeg转码。
如果让HTTP请求一直等待，浏览器可能超时，用户也无法知道当前处理到了哪里。

现在可以把已经上传的源视频和带时间戳转写一次提交给流水线：

```text
客户端提交任务
  ↓ 立即返回 202 + job_id
SQLite 持久化请求和任务状态
  ↓
后台 Worker 调用 LLM 生成切片计划
  ↓ 每完成一个片段就保存一次进度
FFmpeg 依次执行物理裁剪
  ↓
素材中心登记输出文件
  ↓
任务 succeeded，客户端取得 output_asset_ids
```

## API

### 1. 提交任务

```text
POST /api/v1/agents/live-clips/pipelines
X-Idempotency-Key: live-replay-20260728-001
```

请求体示例：

```json
{
  "product_id": "P1001",
  "source_asset_id": "上传源视频后获得的素材ID",
  "transcript": [
    {
      "start_seconds": 0,
      "end_seconds": 8,
      "text": "这款防晒轻薄不黏腻，适合日常通勤。"
    },
    {
      "start_seconds": 8,
      "end_seconds": 16,
      "text": "当前库存充足，可以正常选购。"
    }
  ],
  "max_clips": 2
}
```

接口返回 `202 Accepted`。返回值中的 `id` 是任务编号。

### 2. 查询任务

```text
GET /api/v1/agents/live-clips/pipelines/{job_id}
GET /api/v1/agents/live-clips/pipelines?status=running
```

任务状态依次为：

```text
queued → running → succeeded
                   ↘ failed
```

成功后：

- `planned_asset_ids`：大模型生成的候选切片计划；
- `output_asset_ids`：FFmpeg已经生成并登记的真实MP4素材；
- `transcript_segment_count`：本次处理的转写片段数量。

### 3. 重试失败任务

```text
POST /api/v1/agents/live-clips/pipelines/{job_id}/retry
```

最多尝试3次。已经完成的物理片段不会重新裁剪，任务会从
`output_asset_ids`记录的最近进度继续。

## 工程化保护

- **幂等提交**：相同`X-Idempotency-Key`和相同请求返回同一任务，防止用户重复点击。
- **幂等冲突检测**：同一个键对应不同请求会返回409，避免误把旧任务当成新任务。
- **数据库外键**：源视频被任务引用后不能被误删，避免产生找不到源文件的悬空任务。
- **断点续跑**：计划编号和每个输出编号逐步写入SQLite，失败重试不重复调用模型或重做已完成片段。
- **重启恢复**：服务启动时把意外中断的`running`任务重新放回队列。
- **受控输入**：只接受素材中心上传并登记的本地视频，不让FFmpeg直接访问任意网络地址。
- **人工门禁**：流水线完成只代表生成候选素材，不代表自动发布。

## 当前边界

当前Worker运行在FastAPI单进程内，适合个人作品集和单机演示。多实例生产
环境应把任务执行升级到Redis/Celery、RQ或其他独立任务队列。当前流水线
接收已经带时间戳的转写；批量ASR自动转写仍是下一阶段能力。

## 真实端到端验证

Docker服务构建完成后运行：

```powershell
docker exec ecommerce-ai-core python scripts/test_live_clip_pipeline.py
```

脚本在临时目录生成12秒视频，使用当前配置的真实大模型选择一个高光时间段，
再通过持久化任务服务和真实FFmpeg生成MP4。测试使用内存数据库和临时素材
目录，不污染正式演示数据。

## 面试表述

> 视频转码属于长耗时任务，所以我没有让接口同步等待，而是设计了SQLite持久化任务。提交接口先返回202和任务编号，后台完成大模型选段及多个FFmpeg裁剪，并在每个片段完成后保存进度。如果第二个片段失败，重试时不会重新调用大模型，也不会重复裁第一个片段；服务意外重启后也会把中断任务重新入队。当前是单机Worker实现，我也清楚多实例生产环境需要升级为Redis加Celery等独立队列。
