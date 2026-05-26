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
def generate_image_from_text(prompt: str, save_path: str) -> bool:
    """文生图：基于 prompt 生成锚图"""
    try:
        resp = _client.images.generate(
            model=_config["image_model"],
            prompt=prompt,
            n=1,
            size="1792x1024",
        )
        url = resp.data[0].url if resp.data[0].url else resp.data[0].b64_json
        if url:
            _download_image(url, save_path)
            return True
    except Exception as e:
        print(f"文生图失败: {e}")
    return False


def generate_image_from_ref(ref_image_path: str, prompt_diff: str, save_path: str,
                            aspect_ratio: str = "16:9") -> bool:
    """图生图：基于参考图 + 差异描述 生成套图"""
    try:
        b64_url = encode_image(ref_image_path)

        size_map = {"16:9": "1792x1024", "9:16": "1024x1792"}
        size = size_map.get(aspect_ratio, "1792x1024")

        # 使用 chat.completions 方式调用图生图（多模态图生图）
        resp = _client.chat.completions.create(
            model=_config["image_model"],
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": b64_url}},
                    {"type": "text", "text": f"Generate a photorealistic image based on the reference image with these changes: {prompt_diff}. Maintain the same factory building appearance, surroundings, lighting, and overall style. Aspect ratio {aspect_ratio}. No text, no watermarks, no logos. Photorealistic, high quality."},
                ]
            }],
            max_tokens=4096,
        )

        # 从响应中提取图片
        content = resp.choices[0].message.content
        if content:
            # 尝试提取 base64 图片
            if "data:image" in content:
                img_data = content.split("data:image/")[1]
                img_data = img_data.split(";base64,")[1]
                ext = content.split("data:image/")[1].split(";")[0]
                with open(save_path, "wb") as f:
                    f.write(base64.b64decode(img_data))
                return True
            # 尝试提取 URL
            elif "http" in content:
                import re
                urls = re.findall(r'https?://[^\s<>"]+', content)
                if urls:
                    _download_image(urls[0], save_path)
                    return True

        # 回退：尝试标准 images.generate 方式
        resp2 = _client.images.generate(
            model=_config["image_model"],
            prompt=prompt_diff,
            n=1,
            size=size,
        )
        url = resp2.data[0].url if resp2.data[0].url else resp2.data[0].b64_json
        if url:
            _download_image(url, save_path)
            return True

    except Exception as e:
        print(f"图生图失败: {e}")
    return False


def _download_image(url: str, save_path: str):
    """下载图片到本地"""
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
    """调用 TTS 合成语音，保存为 MP3"""
    try:
        resp = _client.audio.speech.create(
            model=_config["tts_model"],
            voice="alloy",  # 默认男声
            input=text,
            response_format="mp3",
            speed=1.0,
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
