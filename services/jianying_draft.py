"""剪映草稿构建：使用 pyCapCut 创建模式"""
import os
import shutil
import pycapcut as cc
from pycapcut import (
    DraftFolder, VideoSegment, AudioSegment, TextSegment,
    TrackType, trange, TextStyle, ClipSettings
)
from . import load_config

_config = load_config()
DRAFT_DIR = _config["jianying_draft_dir"]


def _find_template_draft() -> str:
    """找到一个真实草稿作为模板（复制其辅助文件结构）"""
    drafts = []
    for name in os.listdir(DRAFT_DIR):
        path = os.path.join(DRAFT_DIR, name)
        if os.path.isdir(path) and not name.startswith('.'):
            has_content = os.path.exists(os.path.join(path, "draft_content.json"))
            has_timeline = os.path.exists(os.path.join(path, "Timelines"))
            if has_content and has_timeline:
                mtime = os.path.getmtime(path)
                drafts.append((mtime, name, path))
    drafts.sort(reverse=True)
    return drafts[0][2] if drafts else None


def _merge_template_files(template_dir: str, draft_dir: str):
    """将模板草稿的辅助文件合并到新草稿"""
    skip = {"draft_content.json", "draft_content.json.bak", "draft_meta_info.json",
            "draft_cover.jpg", "template-2.tmp", ".backup", ".recycle_bin"}
    for item in os.listdir(template_dir):
        if item in skip:
            continue
        src = os.path.join(template_dir, item)
        dst = os.path.join(draft_dir, item)
        if not os.path.exists(dst):
            if os.path.isdir(src):
                shutil.copytree(src, dst)
            else:
                shutil.copy2(src, dst)


def build_draft(project_name: str, project_data: dict, aspect_ratio: str,
                draft_name: str = None) -> dict:
    if draft_name is None:
        draft_name = f"{project_name}_{aspect_ratio.replace(':', 'x')}"

    set_images = [img for img in project_data.get("set_images", [])
                  if img.get("aspect_ratio") == aspect_ratio and img.get("status") == "done"]

    if not set_images:
        return {"success": False, "error": "没有可用于生成草稿的套图"}

    if not os.path.exists(DRAFT_DIR):
        return {"success": False, "error": f"剪映草稿目录不存在: {DRAFT_DIR}"}

    try:
        template = _find_template_draft()

        # 1. 创建草稿核心文件
        folder = DraftFolder(DRAFT_DIR)
        if folder.has_draft(draft_name):
            folder.remove(draft_name)

        w, h = (1920, 1080) if aspect_ratio == "16:9" else (1080, 1920)
        script = folder.create_draft(draft_name, width=w, height=h, fps=30)

        # 总时长：优先用合并口播时长
        merged_dur = project_data.get("narration_duration", 0)
        if merged_dur > 0:
            total_dur = merged_dur
            per_img_dur = merged_dur // len(set_images)
        else:
            per_img_dur = 5_000_000
            total_dur = len(set_images) * per_img_dur

        output_dir = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "output", project_name)

        # 背景音乐轨道
        bgm_path = project_data.get("bgm_path")
        if bgm_path:
            full_bgm = os.path.join(output_dir, bgm_path)
            if os.path.exists(full_bgm):
                script.add_track(TrackType.audio, "背景音乐", relative_index=0)
                seg = AudioSegment(full_bgm, trange("0s", total_dur))
                script.add_segment(seg, "背景音乐")

        # 视频轨道
        script.add_track(TrackType.video, "视频轨道", relative_index=100)

        # 文本轨道
        script.add_track(TrackType.text, "文字", relative_index=200)

        # 合并口播音频轨道 (一条完整音频)
        merged_audio = project_data.get("narration_audio")
        if merged_audio:
            full_audio = os.path.join(output_dir, merged_audio)
            if os.path.exists(full_audio):
                script.add_track(TrackType.audio, "口播", relative_index=300)
                seg = AudioSegment(full_audio, trange("0s", total_dur))
                script.add_segment(seg, "口播")

        # 遍历套图，添加视频和文字片段
        for i, img in enumerate(set_images):
            dur = per_img_dur
            current_time = i * per_img_dur

            img_path = img.get("generated_image") or img.get("custom_image")
            if img_path:
                full_img = os.path.join(output_dir, img_path)
                if os.path.exists(full_img):
                    script.add_segment(
                        VideoSegment(full_img, trange(current_time, dur)),
                        "视频轨道"
                    )

            display_text = img.get("display_text", "")
            if display_text:
                script.add_segment(
                    TextSegment(
                        display_text,
                        trange(current_time, dur),
                        style=TextStyle(size=12, align=1, auto_wrapping=True),
                        clip_settings=ClipSettings(transform_y=-0.7),
                    ),
                    "文字"
                )

        script.save()

        # 2. 复制模板的辅助文件结构
        if template:
            _merge_template_files(template, os.path.join(DRAFT_DIR, draft_name))

        return {
            "success": True,
            "draft_path": script.save_path,
            "draft_name": draft_name,
            "total_duration_us": total_dur,
            "image_count": len(set_images),
            "total_duration_sec": round(total_dur / 1_000_000, 1),
        }

    except Exception as e:
        return {"success": False, "error": str(e)}
