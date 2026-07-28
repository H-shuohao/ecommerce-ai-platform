# 直播切片持久化异步流水线

## 为什么需要异步任务

一次直播回放处理可能包含大模型选段、FFprobe读取时长和多个FFmpeg转码。
如果让HTTP请求一直等待，浏览器可能超时，用户也无法知道当前处理到了哪里。

现在可以只提交已经上传的源视频；如果没有手工转写，流水线会自动提取
音频并调用批量ASR：

```text
客户端提交任务
  ↓ 立即返回 202 + job_id
SQLite 持久化请求和任务状态
  ↓
FFmpeg提取16kHz单声道音频
  ↓
批量ASR生成带时间戳转写并写回任务
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
  "transcript": [],
  "transcript_language": "zh",
  "max_clips": 2
}
```

接口返回 `202 Accepted`。返回值中的 `id` 是任务编号。
`transcript`留空代表自动ASR；已有可靠字幕时也可以继续传入分段数组，
此时系统跳过ASR。

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

`status`表示总体结果，`stage`表示当前正在做什么：

```text
queued → transcribing → planning → cutting → completed
                                      ↘ failed
```

成功后：

- `planned_asset_ids`：大模型生成的候选切片计划；
- `output_asset_ids`：FFmpeg已经生成并登记的真实MP4素材；
- `transcript_segment_count`：本次处理的转写片段数量。
- `transcript_source`：`provided`表示人工提供，`asr`表示系统自动转写。

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
- **ASR结果复用**：自动转写完成后立即写回任务，后续失败重试不会重复转写和重复付费。
- **重启恢复**：服务启动时把意外中断的`running`任务重新放回队列。
- **受控输入**：只接受素材中心上传并登记的本地视频，不让FFmpeg直接访问任意网络地址。
- **人工门禁**：流水线完成只代表生成候选素材，不代表自动发布。

## 当前边界

当前Worker运行在FastAPI单进程内，适合个人作品集和单机演示。多实例生产
环境应把任务执行升级到Redis/Celery、RQ或其他独立任务队列。批量ASR
通过OpenAI兼容的音频转写接口接入，实际运行前需设置：

```text
ASR_PROVIDER=openai-compatible
ASR_API_URL=https://服务商地址/v1/audio/transcriptions
ASR_API_KEY=真实密钥
ASR_MODEL=服务商支持的模型名
```

`ASR_APP_ID`属于RTC实时房间ASR，不能代替上述直播回放批量ASR凭证。

## 真实端到端验证

Docker服务构建完成后运行：

```powershell
docker exec ecommerce-ai-core python scripts/test_live_clip_pipeline.py
```

脚本在临时目录生成12秒带音轨视频，使用真实FFmpeg提取WAV，以确定性测试
Provider模拟ASR服务返回时间戳，再使用当前配置的真实大模型选择高光时间段，
最后通过真实FFmpeg生成MP4。这样可以在没有额外ASR账号费用时验证完整编排；
上线前仍需使用真实ASR凭证做一次识别准确性验收。测试使用内存数据库和临时
素材目录，不污染正式演示数据。

## 面试表述

> 视频转码属于长耗时任务，所以我没有让接口同步等待，而是设计了SQLite持久化任务。用户只需上传回放，后台先用FFmpeg提取标准音频，再由批量ASR生成时间戳，大模型据此选段并调用FFmpeg裁剪。ASR结果和每个片段进度都会落库，失败重试不会重复转写、重复调用大模型或重做已完成片段；服务意外重启后也会把中断任务重新入队。当前是单机Worker实现，我也清楚多实例生产环境需要升级为Redis加Celery等独立队列。
