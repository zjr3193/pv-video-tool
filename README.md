# 光伏短视频内容制作工具

本地 Web 应用，一键将一张厂房屋顶参考图变成全套短视频素材 + CapCut 草稿。

## 核心流程

```
源图上传 → AI识图 → 提示词优化 → 锚图生成 → 批量套图(12张) → 口播文案+TTS → CapCut草稿
```

## 快速开始

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 配置 .env（API Key、模型、草稿目录）
cp .env.example .env

# 3. 启动
python server.py
# 浏览器打开 http://127.0.0.1:8765
```

## 默认套图配置

12 张图，覆盖 6 个场景 × 2 个比例：

| 场景 | 16:9 | 9:16 |
|------|------|------|
| 厂房正门 | ✓ | ✓ |
| 未安装-屋顶 | ✓ | ✓ |
| 安装中-工人装支架 | ✓ | ✓ |
| 安装中-吊车吊组件 | ✓ | ✓ |
| 安装后-屋顶 | ✓ | ✓ |
| 安装前中后对比 | ✓ | ✓ |

## 技术栈

- **后端**: Python FastAPI
- **前端**: Vanilla JS + CSS（深色主题）
- **AI**: gpt-5.5（识图+文本）、gpt-image-2-all（生图）、speech-2.6-hd（TTS）
- **视频**: pyCapCut → CapCut 国际版草稿
- **存储**: JSON 文件（`output/` 目录）

## 环境要求

- Windows 10/11
- Python 3.9+
- CapCut 国际版（非国内剪映）
- FFmpeg（音频拼接）

## 许可

MIT
