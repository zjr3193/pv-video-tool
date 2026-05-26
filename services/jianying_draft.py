"""剪映草稿构建：使用 pyJianYingDraft 创建模式"""
import os
import pyJianYingDraft as draft
from pyJianYingDraft import (
    DraftFolder, VideoMaterial, AudioMaterial,
    VideoSegment, AudioSegment, TextSegment,
    TrackType, trange, tim, TextStyle, ClipSettings
)
from . import load_config

_config = load_config()
DRAFT_DIR = _config["jianying_draft_dir"]


def build_draft(project_name: str, project_data: dict, aspect_ratio: str,
                draft_name: str = None) -> dict:
    """
    构建剪映草稿

    Args:
        project_name: 项目名称
        project_data: 完整的项目数据
        aspect_ratio: "16:9" 或 "9:16"
        draft_name: 草稿名称（可选，默认 项目名_比例）

    Returns:
        {"success": bool, "draft_path": str, "total_duration_us": int}
    """
    if draft_name is None:
        draft_name = f"{project_name}_{aspect_ratio.replace(':', 'x')}"

    # 过滤出选定比例的套图
    set_images = [img for img in project_data.get("set_images", [])
                  if img.get("aspect_ratio") == aspect_ratio and img.get("status") == "done"]

    if not set_images:
        return {"success": False, "error": "没有可用于生成草稿的套图"}

    # 检查草稿目录
    if not os.path.exists(DRAFT_DIR):
        return {"success": False, "error": f"剪映草稿目录不存在: {DRAFT_DIR}"}

    try:
        folder = DraftFolder(DRAFT_DIR)

        # 删除同名草稿
        if folder.has_draft(draft_name):
            folder.remove(draft_name)

        # 画布分辨率
        w, h = (1920, 1080) if aspect_ratio == "16:9" else (1080, 1920)
        script = folder.create_draft(draft_name, width=w, height=h, fps=30)

        # 计算总时长
        total_dur = sum(img.get("audio_duration", 5_000_000) for img in set_images)
        if total_dur == 0:
            total_dur = len(set_images) * 5_000_000  # 默认 5 秒/张

        # 1. 背景音乐轨道
        bgm_path = project_data.get("bgm_path")
        if bgm_path:
            full_bgm = os.path.join(os.path.dirname(DRAFT_DIR), "..", bgm_path)
            if os.path.exists(full_bgm):
                script.add_track(TrackType.audio, "背景音乐", relative_index=0)
                bgm_mat = AudioMaterial(full_bgm)
                script.add_material(bgm_mat)
                script.add_segment(
                    AudioSegment(bgm_mat, target_timerange=trange("0s", total_dur)),
                    "背景音乐"
                )

        # 2. 视频轨道
        script.add_track(TrackType.video, "视频轨道", relative_index=100)

        # 3. 文本轨道
        script.add_track(TrackType.text, "文字", relative_index=200)

        # 4. 口播音频轨道
        script.add_track(TrackType.audio, "口播", relative_index=300)

        # 遍历套图，添加片段
        current_time = 0
        output_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "output", project_name)

        for img in set_images:
            audio_dur = img.get("audio_duration", 5_000_000)  # 微秒
            if audio_dur <= 0:
                audio_dur = 5_000_000

            # 视频片段
            img_path = img.get("generated_image") or img.get("custom_image")
            if img_path:
                full_img = os.path.join(output_dir, img_path)
                if os.path.exists(full_img):
                    img_mat = VideoMaterial(full_img)
                    script.add_material(img_mat)
                    script.add_segment(
                        VideoSegment(img_mat, target_timerange=trange(current_time, audio_dur)),
                        "视频轨道"
                    )

            # 文字片段
            display_text = img.get("display_text", "")
            if display_text:
                script.add_segment(
                    TextSegment(
                        display_text,
                        trange(current_time, audio_dur),
                        style=TextStyle(size=12, align=1, auto_wrapping=True),
                        clip_settings=ClipSettings(transform_y=-0.7),
                    ),
                    "文字"
                )

            # 口播音频
            narration_audio = img.get("narration_audio")
            if narration_audio:
                full_audio = os.path.join(output_dir, narration_audio)
                if os.path.exists(full_audio):
                    audio_mat = AudioMaterial(full_audio)
                    script.add_material(audio_mat)
                    script.add_segment(
                        AudioSegment(audio_mat, target_timerange=trange(current_time, audio_dur)),
                        "口播"
                    )

            current_time += audio_dur

        # 保存
        script.save()

        return {
            "success": True,
            "draft_path": script.save_path,
            "draft_name": draft_name,
            "total_duration_us": current_time,
            "image_count": len(set_images),
            "total_duration_sec": round(current_time / 1_000_000, 1),
        }

    except Exception as e:
        return {"success": False, "error": str(e)}
