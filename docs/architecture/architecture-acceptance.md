# 电商 AI 八项目一键验收

## 为什么需要统一验收

仓库中的单元测试、Agent 评测、MCP 客户端测试和 FFmpeg 冒烟测试原本可以分别运行，但单点通过不能直接证明八个项目能够在同一环境中协同工作。

`scripts/run_architecture_acceptance.py` 将可验证能力整理成统一验收矩阵，输出逐项证据、耗时、失败原因以及 JSON、Markdown 两种报告。

## 八项目验收映射

| 项目 | 主要验收内容 |
|---|---|
| 项目1 Agent Runtime | 服务存活、依赖就绪、`X-Request-ID`、运行指标 |
| 项目2 售前咨询 Agent | 工具发现、历史 Run、真实多轮推荐与库存追问 |
| 项目3 轻量 AI 数据中台 | 统一目录、8项质量规则、版本和缓存指标 |
| 项目4 直播切片 Agent | 异步历史、抽音频、转写编排、LLM规划、FFmpeg切片 |
| 项目5 内容运营 Agent | 异步任务、草稿持久化、真实生成、人工审核门禁 |
| 项目6 MCP 共享层 | 标准 MCP 客户端连接、工具发现、资源读取、工具调用 |
| 项目7 多模态素材中心 | image/video/text检索、来源和商品关联 |
| 项目8 评测与可观测 | 最新固定评测基线、HTTP指标和告警 |

## 两种运行模式

### Quick：日常只读检查

不会创建新的 LLM 任务或视频切片，适合每次启动后快速确认系统状态：

```powershell
docker exec ecommerce-ai-core python scripts/run_architecture_acceptance.py --mode quick
```

### Full：面试演示前完整验收

会实际执行：

- 两轮售前 Agent 对话；
- 一次内容运营异步生成任务；
- 一次 MCP 协议级调用；
- 一次音轨提取、切片规划和 FFmpeg 物理裁剪。

```powershell
docker exec ecommerce-ai-core python scripts/run_architecture_acceptance.py --mode full
```

完整的30条售前评测会产生额外模型调用，因此必须显式开启：

```powershell
docker exec ecommerce-ai-core python scripts/run_architecture_acceptance.py `
  --mode full `
  --run-evaluation
```

## 报告位置

每次运行都会生成：

- `services/ai-core/data/acceptance-reports/*.json`
- `services/ai-core/data/acceptance-reports/*.md`

运行报告属于本地证据，目录默认被 Git 忽略，避免频繁执行产生大量版本文件。需要公开某次结果时，应人工检查并将脱敏摘要放到 `docs/evaluation/`。

## 开启认证后的运行方式

验收器支持管理员 API Key，并会把同一凭据传递给 MCP 客户端：

```powershell
docker exec `
  -e ACCEPTANCE_API_KEY=你的管理员APIKey `
  ecommerce-ai-core `
  python scripts/run_architecture_acceptance.py --mode full
```

脚本不会把 API Key 写入报告。

## 结论含义

- `passed`：本次环境下已真实执行并达到验收条件。
- `warning`：核心链路可用，但存在可选配置或证据缺口。
- `failed`：接口、业务结果或质量门槛不符合预期，命令返回非零退出码。
- `skipped`：当前模式有意跳过高耗时或会产生模型费用的用例。

`pass_rate` 计算已执行且未跳过的用例，警告项不会被伪装成通过。

## 当前边界

完整模式中的直播切片验收会真实运行 FFmpeg、真实调用切片规划模型并登记真实 MP4，但批量 ASR 使用确定性测试 Provider 验证编排和时间戳落库。没有配置真实批量 ASR 凭据前，不能用该结果宣称真实语音识别准确率已经通过验收。

这套验收证明的是当前模拟业务数据和当前环境下的工程闭环，不代表生产并发容量、真实用户规模或第三方服务 SLA。
