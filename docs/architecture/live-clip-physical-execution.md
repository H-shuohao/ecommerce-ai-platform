# 直播切片 Agent：FFmpeg 物理裁剪链路

## 目标

直播切片 Agent 不再只返回“建议从第几秒切到第几秒”，还可以把候选计划真正裁剪成新的 MP4 文件，并登记到多模态素材中心。

职责分工如下：

```text
LLM：阅读带时间戳的转写，挑选值得复用的片段
Backend：校验商品、时间边界、源素材和最大切片时长
FFprobe：读取源视频真实时长
FFmpeg：执行视频裁剪和 H.264/AAC 转码
素材中心：保存输出文件、计算 SHA-256、去重并提供下载
人工审核：决定切片是否可以正式发布
```

## 可验证链路

### 1. 上传源视频

在 Swagger 中调用：

```text
POST /api/v1/assets/upload
```

上传 MP4 文件，并填写标题、商品编号和标签。接口返回素材 `id` 和
`local-asset://...` 格式的 `uri`。

### 2. 生成候选切片计划

调用：

```text
POST /api/v1/agents/live-clips/plan
```

把上传接口返回的 `uri` 填入 `video_uri`，再提供带开始时间、结束时间和文字内容的转写。模型返回一个或多个候选片段，每个片段都有 `asset_id`。

### 3. 执行物理裁剪

选择一个候选片段，调用：

```text
POST /api/v1/agents/live-clips/plans/{planned_asset_id}/execute
```

后端会：

1. 确认该编号来自直播切片 Agent；
2. 从计划地址解析开始和结束时间；
3. 找到素材中心里的源视频；
4. 使用 FFprobe 校验源视频实际时长；
5. 使用 FFmpeg 生成新的 MP4；
6. 对文件进行类型、大小和 SHA-256 校验；
7. 把生成文件登记为 `live-clip-agent-ffmpeg` 来源的素材。

返回结果中的 `physical_cut_completed=true` 表示物理文件已经生成，
`human_review_required=true` 表示它仍需运营人员审核。

### 4. 下载结果

从执行接口返回值中取得 `output_asset.id`，调用：

```text
GET /api/v1/assets/{asset_id}/content
```

即可下载生成的 MP4 文件。

## 安全与稳定性边界

- 只允许处理素材中心已经保存的本地视频，不直接让 FFmpeg访问任意网络地址。
- 不使用 shell 拼接命令，FFmpeg参数通过固定列表传入，降低命令注入风险。
- 输入和输出路径都必须落在素材中心的受控目录中。
- 执行前校验开始时间、结束时间、源视频时长和单段最大时长。
- FFmpeg执行有超时限制，错误会转换成明确的 HTTP 状态码。
- 生成文件继续复用素材中心的文件签名校验、大小限制和 SHA-256 去重。
- 物理切片完成不等于自动发布，仍保留人工审核门禁。

## 配置项

```dotenv
FFMPEG_BINARY=ffmpeg
FFPROBE_BINARY=ffprobe
FFMPEG_TIMEOUT_SECONDS=120
LIVE_CLIP_MAX_DURATION_SECONDS=300
```

Docker 镜像会安装 FFmpeg。本机直接运行 Python 服务时，需要自行安装
FFmpeg，或者把 `FFMPEG_BINARY`、`FFPROBE_BINARY` 指向可执行文件。

## 独立端到端验证

Docker 启动后可执行：

```powershell
docker exec ecommerce-ai-core python scripts/test_live_clip_ffmpeg.py
```

脚本会在临时目录生成3秒测试视频，使用真实FFmpeg裁剪0.5秒到2秒的
片段，并校验输出时长、MIME类型和物理文件。它使用内存数据库和临时
素材目录，不污染正式演示数据。

## 面试表述

可以概括为：

> 大模型只负责语义判断，也就是从转写中选出高光时间段；后端负责确定性校验，FFmpeg负责真正执行视频裁剪，最终文件交给素材中心做持久化、哈希去重和下载。这样既利用了大模型的理解能力，也避免让模型直接控制文件系统或随意执行命令。
