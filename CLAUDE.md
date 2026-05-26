# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

光伏短视频内容制作工具 —— 本地 Web 应用。用户上传一张厂房屋顶参考图，AI 自动：识图分析 → 生成锚图 → 批量生成 12 张多视角套图 → 写口播文案 → TTS 合成语音 → 构建 CapCut 草稿。

技术栈：Python FastAPI 后端 + Vanilla JS/CSS 前端 + JSON 文件存储。

## 常用命令

```bash
python server.py        # 启动服务 (127.0.0.1:8765)
启动.bat                # Windows 一键启动（自动杀旧进程）
```

无测试套件，无 lint 配置。验证靠手动走流程。

## 架构概览

```
.env                        # API密钥、模型名、草稿目录
server.py                   # FastAPI 主服务（所有端点）
services/
  __init__.py               # 加载 .env 配置
  api_client.py             # 识图/生图/文本/TTS API 封装
  project.py                # 项目管理（JSON 读写）
  jianying_draft.py         # CapCut 草稿构建（pyCapCut）
  logger.py                 # 日志（文件 + 内存200条缓冲）
static/
  index.html                # 首页 - 项目列表
  project.html              # 7步工作台（核心页面）
  settings.html             # 只读设置页
  logs.html                 # 日志查看器
output/                     # 项目输出（gitignore）
```

**数据流**：前端 → FastAPI → OpenAI 兼容网关 (`ai.t8star.org/v1`) → 识图/生图/文本/TTS

**项目存储**：`output/<日期>/project.json` + `images/` + `audio/`，无数据库。

## 关键 API 端点（7步流程）

| 步骤 | 端点 | 说明 |
|------|------|------|
| 1 | `POST /api/projects/{name}/upload-source` | 上传源图 |
| 2 | `POST /api/projects/{name}/analyze-vision` | gpt-5.5 识图 |
| 3 | `POST /api/projects/{name}/generate-prompt` | 生成锚图提示词 |
| 4 | `POST /api/projects/{name}/generate-anchor` | 文生图锚图 |
| 5 | `POST /api/projects/{name}/generate-set` | 批量图生图(4路并发，异步轮询) |
| 6 | `POST /api/projects/{name}/generate-narrations` | 批量口播文案 |
| 6 | `POST /api/projects/{name}/synthesize-tts` | 逐条TTS → ffmpeg拼接 |
| 7 | `POST /api/projects/{name}/build-draft` | 构建CapCut草稿 |

日志：`GET /api/logs`、`GET /api/logs/files`、`GET /api/logs/files/{name}`

## 核心约束

1. **图片永不删除** — 重新生成时旧图移至 `images/discarded/`，加时间戳后缀
2. **绕过系统代理** — `services/api_client.py` 中 `_http = requests.Session(); _http.trust_env = False`，所有 HTTP 调用必须走这个 session
3. **异步长任务** — 生图/TTS 提交到 `ThreadPoolExecutor` 后台跑，前端 `setInterval` 轮询 `project.json` 状态
4. **CapCut 国际版** — 草稿生成用 `pycapcut` 库，目标目录在 `.env` 的 `JIANYING_DRAFT_DIR`（默认 `E:\capcut_Drafts\CapCut Drafts`）。国际版不加密草稿；国内剪映加密，pycapcut 不支持
5. **前端口播+合成已合并** — 步骤6一键完成文案生成+TTS合成，无独立语音合成步骤
6. **TTS 调用方式** — 参考 `F:\光伏项目\CLAUDE.md`：`model="speech-2.6-hd"`, `voice="presenter_male"`, `speed=1.3`，用 OpenAI SDK `stream_to_file()`
7. **MP3 拼接** — 用 ffmpeg concat（硬编码路径 `C:\Users\Administrator\bin\ffmpeg`），pydub 不兼容 Python 3.14
8. **HTML 缓存已禁用** — 全局 `no-cache` 中间件，HTML 页面走路由而非 StaticFiles

## 前端关键模式

- `api(endpoint, opts)` — fetch 封装，非 2xx 抛 Error 含 `detail`/`error` 字段
- 弹窗：`modalContainer.innerHTML` 注入 HTML + `onclick="this.remove()"` 关闭遮罩
- 文件选择：JS 动态 `createElement('input')` + `.click()`（弹窗 innerHTML 内的隐藏 input 不可靠）
- 步骤回退：可自由点击已完成的步骤跳转，修改前序步骤时后续标记"待更新"（不自动删除）
