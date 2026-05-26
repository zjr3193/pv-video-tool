"""光伏短视频工具 — API 服务模块"""

# ============================================
# 配置加载
# ============================================
def load_config():
    """从 .env 加载配置"""
    import os
    from dotenv import load_dotenv
    load_dotenv()
    return {
        "openai_api_key": os.getenv("OPENAI_API_KEY", ""),
        "openai_base_url": os.getenv("OPENAI_BASE_URL", ""),
        "image_model": os.getenv("OPENAI_IMAGE_MODEL", "gpt-image-2-all"),
        "gpt_model": os.getenv("OPENAI_GPT_MODEL", "gpt-5.5"),
        "gemini_image_model": os.getenv("GEMINI_IMAGE_MODEL", "gemini-3.1-flash-image-preview-2k"),
        "tts_model": os.getenv("minimax_text2voice_model", "minimax/speech-2.6-hd"),
        "jianying_draft_dir": os.getenv("JIANYING_DRAFT_DIR", r"E:\JianyingPro Drafts"),
    }
