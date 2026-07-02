# 视频治理平台 MVP

这是基于 `docs/technical-design.md` 收敛实现的可运行 MVP：单租户、global 法域、异步机审流水线 + 人审闭环。

本实现刻意不包含：

- CSAM 检测和 critical 升级
- 7 档处置矩阵
- `need_more_context`
- 多租户或多法域路由

人审最终裁定只有两态：`pass` 和 `block`。

内容摄取接口只负责快速入库和排队。后台 worker 会异步生成证据包、关键词规则命中、维度判断、推荐动作和置信度。机审明确 `auto_pass` / `auto_block` / `critical_escalate` 时直接形成最终准出或拦截结果；只有 `needs_human_review` 的不确定内容才进入人审队列，由人工提交最终裁定。

当前 worker 仍是标准库实现的本地轻量 worker，用来打通生产形态的异步骨架；正式运行数据库统一为 PostgreSQL，启动服务必须配置 `DATABASE_URL`。SQLite 仅保留给自动化测试显式传入临时 `db_path` 时使用。

## 启动

正式运行（PostgreSQL）:

```powershell
python -m pip install -r requirements.txt
docker compose -f docker-compose.postgres.yml up -d
$env:DATABASE_URL="postgresql://vgp:vgp_dev_password@127.0.0.1:5432/vgp"
python backend/run.py
```

打开 http://127.0.0.1:8000。交互式 API 文档在 http://127.0.0.1:8000/docs。
PostgreSQL 模式会自动建表；未配置 `DATABASE_URL` 时服务会拒绝启动。

## 数据库迁移（Alembic）

结构由 `backend/app/models.py` 定义，变更走 Alembic：

```powershell
cd backend
$env:DATABASE_URL="postgresql://vgp:vgp_dev_password@127.0.0.1:5432/vgp"
python -m alembic upgrade head        # 应用迁移
# 改了 models.py 后：
python -m alembic revision --autogenerate -m "describe change"
```

## 异步流水线（Celery + Redis）

机审流水线拆成一条独立可重试的 Celery chain：`extract_evidence -> run_machine_review`，
每阶段幂等，重试耗尽写入死信队列（`GET /api/v1/system/dead-letters`）。

- **未配置 broker**（默认）：Celery 处于 eager 模式，`ingest` 只入队，由 `drain` / 本地线程 worker 同步执行——无需 Redis，测试即走此路径。
- **配置了 broker**：`ingest` 异步派发 chain，由独立 Celery worker 处理。

```powershell
docker compose -f docker-compose.postgres.yml up -d   # 含 postgres + redis
$env:DATABASE_URL="postgresql://vgp:vgp_dev_password@127.0.0.1:5432/vgp"
$env:REDIS_URL="redis://127.0.0.1:6379/0"
# 终端 A：Celery worker
cd backend; celery -A app.tasks worker -Q pipeline -l info
# 终端 B：API
python backend/run.py
```

## 机审与证据提取

当前机审链路已经从纯模拟升级为可插拔实现：

- 视频来源支持远程 URL、本地路径和 `file://` 路径。
- 本地文件会被写入本地对象存储目录，按 SHA256 文件名去重，并提取文件大小、SHA256、扩展名和 MIME 类型。
- 远程 URL 默认只记录引用，不主动下载；需要下载时显式开启 `VGP_ENABLE_REMOTE_DOWNLOAD=true`。
- 媒体文件有大小上限，默认 `VGP_MAX_MEDIA_BYTES=524288000`，超过上限会降级为文本证据，不会拖垮 worker。
- 如果机器安装了 `ffprobe`，会补充时长、分辨率和编码信息。
- 如果机器安装了 `ffmpeg`，会尝试抽取最多 3 张关键帧到 `data/evidence/{content_id}`。
- ASR/OCR/视觉目标检测支持外部 HTTP 模型服务；未配置时会记录 `not_configured` 并使用描述、标题和通用场景标签作为 fallback。
- LLM 机审使用 OpenAI-compatible Chat Completions 接口。每个策略维度（通用策略 / 博彩 / 毒品暴力 / 未成年合规 / 营销画风 / 内容匹配）都用各自的 `build_prompt` 独立调用 LLM 作答；未配置 API Key、熔断器打开或单次调用失败时，该维度自动回退到本地关键词规则，互不影响。

启用 LLM 机审：

```powershell
$env:LLM_API_KEY="your_api_key"
$env:LLM_MODEL="gpt-4o-mini"
$env:LLM_BASE_URL="https://api.openai.com/v1"
python backend/run.py
```

也可以使用 `OPENAI_API_KEY`、`OPENAI_MODEL`、`OPENAI_BASE_URL`。LLM/规则引擎共同产出机审维度结论；机审可直接终局通过或拦截，不确定内容才作为人审建议进入队列。对外最终裁定只允许 `pass` 或 `block`。

媒体落地配置：

```powershell
$env:VGP_MEDIA_DIR="data/media_assets"
$env:VGP_MAX_MEDIA_BYTES="524288000"
$env:VGP_COPY_LOCAL_MEDIA="true"
$env:VGP_ENABLE_REMOTE_DOWNLOAD="false"
$env:VGP_REMOTE_DOWNLOAD_TIMEOUT_SECONDS="30"
```

模态模型服务配置：

```powershell
$env:VGP_ASR_MODEL_URL="http://127.0.0.1:9001/asr"
$env:VGP_OCR_MODEL_URL="http://127.0.0.1:9002/ocr"
$env:VGP_VISION_MODEL_URL="http://127.0.0.1:9003/vision"
$env:VGP_MODEL_API_KEY=""
$env:VGP_MODEL_TIMEOUT_SECONDS="30"
```

ASR 服务返回 `segments`，OCR 服务返回 `items`，视觉服务返回 `objects` 和 `scenes`。系统会把这些响应归一化到 `asr_transcript`、`ocr_results`、`object_detections` 和 `scene_tags`。

## 全链路验证

```powershell
python scripts/smoke_test.py
```

`scripts/smoke_test.py` 会显式使用临时 SQLite 数据库，只用于快速验证代码链路。正式服务和 PostgreSQL 集成验证请配置 `DATABASE_URL` 后运行 `python scripts/postgres_smoke_test.py`。

## API

- `GET /api/v1/health`
- `GET /api/v1/config`
- `GET /api/v1/dashboard/summary`
- `GET /api/v1/pipeline/jobs?offset=0&limit=50`
- `POST /api/v1/pipeline/drain`
- `GET /api/v1/machine/reviews?offset=0&limit=50`
- `GET /api/v1/machine/reviews/{content_id}`
- `POST /api/v1/content/upload`
- `POST /api/v1/content/batch`
- `GET /api/v1/review/human/queue?offset=0&limit=20`
- `GET /api/v1/review/human/{task_id}`
- `POST /api/v1/review/human/{task_id}/claim`
- `POST /api/v1/review/human/{task_id}/decide`
- `GET /api/v1/evidence/{evidence_package_id}`
- `GET /api/v1/evidence/{evidence_package_id}/frames/{frame_id}`
- `GET /api/v1/audit?content_id={content_id}`
- `POST /api/v1/dev/seed`
- `POST /api/v1/dev/reset`

## 模型网关（下一阶段）

本项目现在提供一个独立的模型接入网关：

```powershell
python -m backend.model_gateway
```

默认监听 `http://127.0.0.1:9001`，同时提供：

- `POST /asr`
- `POST /ocr`
- `POST /vision`
- `GET /health`

主治理服务只需要把三类模型 URL 指向同一个网关：

```powershell
$env:VGP_ASR_MODEL_URL="http://127.0.0.1:9001/asr"
$env:VGP_OCR_MODEL_URL="http://127.0.0.1:9001/ocr"
$env:VGP_VISION_MODEL_URL="http://127.0.0.1:9001/vision"
```

无外部密钥时，网关使用 `local` 启发式模式，保证全链路可以运行，并在证据包的 `modality_model_invocations` 里标记 `provider=local_heuristic` 和 warnings。接真实服务时无需改主系统代码：

```powershell
# OCR / Vision 接 Azure AI Vision
$env:MODEL_GATEWAY_OCR_PROVIDER="azure_vision"
$env:MODEL_GATEWAY_VISION_PROVIDER="azure_vision"
$env:AZURE_VISION_ENDPOINT="https://<your-resource>.cognitiveservices.azure.com"
$env:AZURE_VISION_KEY="<your-key>"

# ASR/OCR 接腾讯云语音识别和文字识别
$env:MODEL_GATEWAY_ASR_PROVIDER="tencent_asr"
$env:MODEL_GATEWAY_OCR_PROVIDER="tencent_ocr"
$env:TENCENTCLOUD_SECRET_ID="<your-secret-id>"
$env:TENCENTCLOUD_SECRET_KEY="<your-secret-key>"
$env:TENCENTCLOUD_REGION="ap-guangzhou"
$env:TENCENT_ASR_ENGINE="16k_zh"
$env:TENCENT_ASR_VOICE_FORMAT="wav"
$env:TENCENT_OCR_ACTION="GeneralBasicOCR"
# 如果 ffmpeg 没有进入 PATH，短视频 ASR 抽音频时需要显式指定
$env:MODEL_GATEWAY_FFMPEG_PATH="D:\Github\video-governance-platform\.cache\ffmpeg\ffmpeg-8.1.1-essentials_build\bin\ffmpeg.exe"

# 或者转发到任意自定义 ASR/OCR/Vision HTTP 服务
$env:MODEL_GATEWAY_ASR_PROVIDER="upstream"
$env:MODEL_GATEWAY_ASR_UPSTREAM_URL="http://127.0.0.1:9101/asr"
$env:MODEL_GATEWAY_UPSTREAM_API_KEY="<optional-key>"
```

当前网关只负责普通 ASR/OCR/视觉特征接入，不启用 CSAM、critical 检测、七档处置矩阵或 `need_more_context`。

## 批量摄取与压测

批量入口用于把海量输入拆成受控的小批次入队。接口只负责创建内容和流水线任务，不在 HTTP 请求中执行视频处理：

```powershell
Invoke-RestMethod -Method POST -Uri http://127.0.0.1:8000/api/v1/content/batch `
  -ContentType 'application/json' `
  -Body '{"items":[{"title":"批量视频 1","description":"普通视频","creator_id":"creator_batch"}]}'
```

默认单批上限为 `VGP_MAX_BATCH_INGEST_ITEMS=100`，后台总 backlog 仍受 `VGP_MAX_PIPELINE_BACKLOG` 保护。

可用压测脚本批量创建任务：

```powershell
python scripts/load_test.py --count 200 --batch-size 50
python scripts/load_test.py --count 50 --batch-size 10 --drain
```

压测脚本默认只提交远程视频引用，不下载视频文件；如果开启 `--drain`，会要求 API 处理队列中的任务，用于验证端到端吞吐。

生成本地测试视频：

```powershell
python scripts/generate_test_videos.py --count 120 --output-dir data/test_videos
```

如果 ffmpeg 没有进入系统 PATH，可以显式指定项目缓存里的二进制：

```powershell
$ffmpeg = ".cache\ffmpeg\ffmpeg-8.1.1-essentials_build\bin\ffmpeg.exe"
python scripts/generate_test_videos.py --count 120 --output-dir data/test_videos --ffmpeg-bin $ffmpeg
```

用本地测试视频压测摄取接口：

```powershell
python scripts/load_test.py --count 120 --batch-size 50 --video-dir data/test_videos
```

如果要让后端使用项目缓存里的 ffmpeg/ffprobe 做视频探测和抽帧，启动主服务前配置：

```powershell
$env:VGP_FFMPEG_PATH="D:\Github\video-governance-platform\.cache\ffmpeg\ffmpeg-8.1.1-essentials_build\bin\ffmpeg.exe"
$env:VGP_FFPROBE_PATH="D:\Github\video-governance-platform\.cache\ffmpeg\ffmpeg-8.1.1-essentials_build\bin\ffprobe.exe"
```
