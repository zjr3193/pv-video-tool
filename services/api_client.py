"""API 客户端封装：识图、文本生成、图片生成、TTS"""
import os
import base64
import time
import requests
from openai import OpenAI
from . import load_config

_config = load_config()

# 共享 OpenAI 客户端
_client = OpenAI(
    api_key=_config["openai_api_key"],
    base_url=_config["openai_base_url"],
)


def encode_image(image_path: str) -> str:
    """将本地图片编码为 base64 data URL"""
    with open(image_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("utf-8")
    ext = os.path.splitext(image_path)[1].lower().replace(".", "")
    mime = {"jpg": "jpeg", "jpeg": "jpeg", "png": "png", "webp": "webp"}.get(ext, "jpeg")
    return f"data:image/{mime};base64,{b64}"


# ============================================
# 识图分析 (gpt-5.5 Vision)
# ============================================
VISION_PROMPT = """请详细分析这张图片中的建筑和环境：
1. 主体建筑类型（厂房/仓库/办公楼）、层数、外观特征（外墙颜色、材质）
2. 屋顶特征：面积大小、结构类型（平顶/坡顶）、已安装光伏板的位置和规模
3. 周边环境：是否在工业园区、是否有其他厂房、道路、绿化、围墙
4. 配套设施：是否有空调外机、变压器、停车场、装卸货区等
5. 整体氛围：是否有运行中的感觉（有人、有车、有设备运转痕迹）
请用简洁的中文描述，作为后续AI生成图片的参考信息。
如果有不确定的特征，标注为"疑似"。"""


def analyze_vision(image_path: str) -> str:
    """调用 gpt-5.5 分析图片"""
    b64_url = encode_image(image_path)
    resp = _client.chat.completions.create(
        model=_config["gpt_model"],
        messages=[{
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": b64_url, "detail": "high"}},
                {"type": "text", "text": VISION_PROMPT},
            ]
        }],
        temperature=0.3,
        max_tokens=2000,
    )
    return resp.choices[0].message.content.strip()


# ============================================
# 提示词优化 Agent (gpt-5.5)
# ============================================
PROMPT_OPTIMIZE_TEMPLATE = """你是一个专业的AI图片生成提示词工程师。请基于以下建筑描述，生成一个高质量的文生图提示词。

【建筑描述】
{vision_result}

【要求】
1. 目标：生成一张中国广东工业园区的工商业厂房外观图，用于光伏短视频的背景图
2. 画面中不能出现任何文字、logo、水印、明显的品牌标识
3. 建筑要有空调外机、厂房外观真实、不能像无人区，要有运行中的感觉
4. 周边环境要真实：有道路、绿化、隔壁厂房、车辆等
5. 天气晴朗、白天、自然光线
6. 画质高清、写实风格
7. 图片比例：16:9

请输出：
1. 英文prompt（用于文生图API）
2. 中文版（方便阅读）

格式：
英文prompt：
<英文内容>

中文版本：
<中文内容>"""


def generate_anchor_prompt(vision_result: str) -> dict:
    """生成锚图提示词"""
    resp = _client.chat.completions.create(
        model=_config["gpt_model"],
        messages=[{"role": "user", "content": PROMPT_OPTIMIZE_TEMPLATE.format(vision_result=vision_result)}],
        temperature=0.7,
        max_tokens=2000,
    )
    text = resp.choices[0].message.content.strip()

    # 解析英文和中文部分
    en_prompt = ""
    cn_prompt = ""
    if "英文prompt：" in text:
        parts = text.split("英文prompt：", 1)[1]
        if "中文版本：" in parts:
            en_text, cn_text = parts.split("中文版本：", 1)
            en_prompt = en_text.strip()
            cn_prompt = cn_text.strip()
    else:
        en_prompt = text
        cn_prompt = text

    return {"en_prompt": en_prompt, "cn_prompt": cn_prompt, "raw": text}


# ============================================
# 口播文案生成 (gpt-5.5)
# ============================================
NARRATION_TEMPLATE = """你是一个光伏行业的短视频文案。请基于以下图片场景，写一段15~30秒的口播文案。

【场景】{scene}
【视角】{view_angle}
【参考信息】{vision_result}

要求：
1. 第一人称，投资方视角
2. 语气：专业、可信赖、不浮夸
3. 内容结构：描述场景 → 强调光伏投资价值 → 号召居间人联系
4. 字数：80~150字
5. 不出现具体公司名称、电话、微信号（后续用户自行添加）

只输出口播文案纯文本。"""


def generate_narration(scene: str, view_angle: str, vision_result: str) -> str:
    """生成单张口播文案"""
    resp = _client.chat.completions.create(
        model=_config["gpt_model"],
        messages=[{"role": "user", "content": NARRATION_TEMPLATE.format(
            scene=scene, view_angle=view_angle, vision_result=vision_result
        )}],
        temperature=0.8,
        max_tokens=500,
    )
    return resp.choices[0].message.content.strip()


# ============================================
# 图片生成 (gpt-image-2-all)
# ============================================

def generate_image_from_text(prompt: str, save_path: str) -> dict:
    """文生图：基于 prompt 生成锚图。返回 {success, path|error, raw_response}"""
    try:
        resp = _client.images.generate(
            model=_config["image_model"],
            prompt=prompt,
            n=1,
            size="1792x1024",
        )
        # 检查是否异步任务
        task_id = getattr(resp, 'id', None) or _extract_task_id(resp)
        if task_id:
            return _poll_and_download(task_id, save_path)

        url = _extract_url(resp)
        if url:
            _download_image(url, save_path)
            return {"success": True, "path": save_path}
        return {"success": False, "error": "未从响应中提取到图片URL", "raw": str(resp)[:500]}
    except Exception as e:
        return {"success": False, "error": str(e)}


def generate_image_from_ref(ref_image_path: str, prompt_diff: str, save_path: str,
                            aspect_ratio: str = "16:9") -> dict:
    """图生图：基于参考图 + 差异描述 生成套图。API 同步返回图片URL，单次耗时约60-120s。
    返回 {success, path|error}
    """
    size_map = {"16:9": "1792x1024", "9:16": "1024x1792"}
    size = size_map.get(aspect_ratio, "1792x1024")

    max_retries = 2
    for attempt in range(max_retries):
        try:
            b64_url = encode_image(ref_image_path)
            import requests as req
            resp = req.post(
                f"{_config['openai_base_url']}/images/generations",
                headers={
                    "Authorization": f"Bearer {_config['openai_api_key']}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": _config["image_model"],
                    "prompt": prompt_diff,
                    "n": 1,
                    "size": size,
                    "image": b64_url,
                    "response_format": "url",
                },
                timeout=180,
            )
            data = resp.json()
            _log_api("图生图", data)

            url = _extract_url_from_dict(data)
            if url:
                _download_image(url, save_path)
                return {"success": True, "path": save_path}

            error_msg = data.get("error", {}).get("message", "") or str(data)[:300]
            return {"success": False, "error": error_msg}

        except Exception as e:
            if attempt < max_retries - 1:
                print(f"图生图重试 {attempt+1}/{max_retries}: {e}")
                time.sleep(3)
            else:
                return {"success": False, "error": str(e)}


def _extract_task_id(resp) -> str:
    """从 images.generate 响应中提取异步 task_id"""
    try:
        if hasattr(resp, 'id') and resp.id:
            return resp.id
        return None
    except:
        return None


def _extract_url(resp) -> str:
    """从 images.generate 响应中提取图片 URL"""
    try:
        if resp.data and len(resp.data) > 0:
            item = resp.data[0]
            return item.url or item.b64_json
    except:
        pass
    return None


def _extract_url_from_dict(data: dict) -> str:
    """从 JSON 字典中提取图片 URL"""
    # 标准 OpenAI 格式: {"data": [{"url": "..."}]}
    items = data.get("data", [])
    if items and isinstance(items, list) and len(items) > 0:
        item = items[0]
        url = item.get("url") or item.get("b64_json")
        if url:
            return url
    # 某些网关直接返回 URL 字符串
    url = data.get("url")
    if url:
        return url
    return None


def _poll_and_download(task_id: str, save_path: str, timeout: int = 180) -> dict:
    """轮询异步生图任务，完成后下载"""
    return _poll_task_http(task_id, save_path, timeout)


def _poll_task_http(task_id: str, save_path: str, timeout: int = 180) -> dict:
    """通过 HTTP 轮询异步任务"""
    import requests as req
    import time as _time
    start = _time.time()
    while _time.time() - start < timeout:
        try:
            r = req.get(
                f"{_config['openai_base_url']}/tasks/{task_id}",
                headers={"Authorization": f"Bearer {_config['openai_api_key']}"},
                timeout=30,
            )
            if r.status_code == 200:
                data = r.json()
                status = data.get("status", "")
                if status in ("succeeded", "completed", "done"):
                    url = _extract_url_from_dict(data)
                    if url:
                        _download_image(url, save_path)
                        return {"success": True, "path": save_path}
                    # 可能图片在 output 字段
                    output = data.get("output", {})
                    url = _extract_url_from_dict(output)
                    if url:
                        _download_image(url, save_path)
                        return {"success": True, "path": save_path}
                elif status in ("failed", "cancelled", "error"):
                    return {"success": False, "error": f"生图任务失败: status={status}"}
            elif r.status_code == 404:
                # 任务ID不存在，可能不是异步接口，退回
                return {"success": False, "error": f"任务 {task_id[:20]}... 不存在(404)"}
        except Exception as e:
            print(f"轮询异常: {e}")
        _time.sleep(3)
    return {"success": False, "error": f"轮询超时({timeout}s)"}


def _log_api(name: str, data: dict):
    """打印 API 响应摘要用于调试"""
    summary = str(data)[:400] if data else "None"
    print(f"[API] {name}: {summary}")


def _download_image(url: str, save_path: str):
    """下载图片到本地"""
    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    if url.startswith("data:"):
        b64_data = url.split(",", 1)[1]
        with open(save_path, "wb") as f:
            f.write(base64.b64decode(b64_data))
    else:
        resp = requests.get(url, timeout=60)
        resp.raise_for_status()
        with open(save_path, "wb") as f:
            f.write(resp.content)


# ============================================
# TTS 语音合成 (MinMax via 网关)
# ============================================
def synthesize_tts(text: str, save_path: str) -> bool:
    """调用 TTS 合成语音（参考 F:\光伏项目 的调用方式），保存为 MP3"""
    try:
        # 参考项目: model="speech-2.6-hd", voice="presenter_male", speed=1.3
        resp = _client.audio.speech.create(
            model="speech-2.6-hd",
            voice="presenter_male",
            input=text,
            speed=1.3,
        )
        resp.stream_to_file(save_path)
        return True
    except Exception as e:
        print(f"TTS 合成失败: {e}")
        return False


def get_audio_duration_ms(audio_path: str) -> int:
    """获取音频时长（微秒）"""
    try:
        from pymediainfo import MediaInfo
        info = MediaInfo.parse(audio_path)
        for track in info.tracks:
            if track.track_type == "Audio" or track.track_type == "General":
                dur = getattr(track, "duration", None)
                if dur:
                    return int(float(dur))  # 毫秒 → 微秒需要*1000，但 pymediainfo 返回的是毫秒
        return 0
    except:
        pass
    # 回退：用 mutagen
    try:
        from mutagen.mp3 import MP3
        audio = MP3(audio_path)
        return int(audio.info.length * 1_000_000)
    except:
        return 0
