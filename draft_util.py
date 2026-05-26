"""
剪映草稿工具 —— 素材提取 & 草稿重建
利用 pyJianYingDraft 从剪映草稿中提取信息并构建新草稿

用法:
    python draft_util.py extract    # 提取最新草稿的素材信息
    python draft_util.py rebuild    # 使用测试素材重建草稿
    python draft_util.py demo       # 完整演示: 提取 + 重建
"""
import pyJianYingDraft as draft
from pyJianYingDraft import (
    DraftFolder, ScriptFile, VideoMaterial, AudioMaterial,
    VideoSegment, AudioSegment, TextSegment, TrackType,
    trange, tim, ClipSettings, TextStyle
)
import os
import sys
import json
import glob
from datetime import datetime

# ============================================
# 配置
# ============================================
DRAFT_DIR = r"E:\JianyingPro Drafts"


def find_latest_draft() -> str:
    """找到最新修改的草稿"""
    drafts = []
    for name in os.listdir(DRAFT_DIR):
        path = os.path.join(DRAFT_DIR, name)
        if os.path.isdir(path) and not name.startswith('.'):
            mtime = os.path.getmtime(path)
            drafts.append((mtime, name, path))
    drafts.sort(reverse=True)
    return drafts[0] if drafts else None


def inspect_draft_structure(draft_path: str) -> dict:
    """检查草稿目录结构，提取可读的元数据"""
    info = {
        "name": os.path.basename(draft_path),
        "path": draft_path,
        "readable_files": {},
        "encrypted_files": [],
        "timeline_info": None,
        "settings": None,
        "resources": [],
    }

    # 扫描所有文件
    for root, dirs, files in os.walk(draft_path):
        for f in files:
            fpath = os.path.join(root, f)
            rel = os.path.relpath(fpath, draft_path)

            if f.endswith('.json') and not f.endswith('.bak'):
                try:
                    with open(fpath, 'r', encoding='utf-8') as fh:
                        data = json.load(fh)
                    info["readable_files"][rel] = data
                except (json.JSONDecodeError, UnicodeDecodeError):
                    info["encrypted_files"].append(rel)

            elif f == 'draft_settings':
                try:
                    with open(fpath, 'r', encoding='utf-8') as fh:
                        info["settings"] = fh.read()
                except:
                    pass

    # 解析可读的关键信息
    for rel, data in info["readable_files"].items():
        if 'project.json' in rel and 'Timelines' in rel:
            info["timeline_info"] = data
        if 'draft_biz_config.json' in rel:
            info["biz_config"] = data

    return info


def extract_cover(draft_path: str, output_dir: str) -> str:
    """提取草稿封面图"""
    cover_path = os.path.join(draft_path, "draft_cover.jpg")
    if os.path.exists(cover_path):
        import shutil
        dest = os.path.join(output_dir, "cover.jpg")
        shutil.copy(cover_path, dest)
        return dest
    return None


def create_test_draft():
    """使用 pyJianYingDraft 从零创建测试草稿（验证草稿生成能力）"""
    print("\n" + "=" * 60)
    print("创建测试草稿")
    print("=" * 60)

    folder = DraftFolder(DRAFT_DIR)

    # 清理旧测试草稿
    test_name = "AI_Test_Rebuild"
    if folder.has_draft(test_name):
        folder.remove(test_name)
        print(f"  已删除旧草稿: {test_name}")

    # 创建新草稿 (1080x1920 竖屏, 30fps)
    script = folder.create_draft(test_name, width=1080, height=1920, fps=30)
    print(f"  草稿已创建: {test_name}")
    print(f"  画布: {script.width}x{script.height}, FPS: {script.fps}")

    # 检查本地是否有可用的测试素材
    test_video = None
    test_audio = None
    for path in [
        r"F:\光伏-图生视频工具\test_video.mp4",
        r"E:\test_video.mp4",
    ]:
        if os.path.exists(path):
            test_video = path
            break

    # 添加视频轨道
    video_track_name = "视频轨道"
    script.add_track(TrackType.video, video_track_name)

    if test_video:
        video_mat = VideoMaterial(test_video)
        script.add_material(video_mat)
        video_seg = VideoSegment(
            video_mat,
            target_timerange=trange("0s", "5s"),
            source_timerange=trange("0s", "5s"),
        )
        script.add_segment(video_seg, video_track_name)
        print(f"  已添加视频素材: {os.path.basename(test_video)}, 5秒")

    # 添加音频轨道
    audio_track_name = "音频轨道"
    script.add_track(TrackType.audio, audio_track_name)

    # 尝试查找系统自带的测试音频，或跳过
    has_audio = False
    for audio_path in [
        r"C:\Windows\Media\Alarm01.wav",
        r"C:\Windows\Media\Windows Notify.wav",
    ]:
        if os.path.exists(audio_path):
            audio_mat = AudioMaterial(audio_path)
            script.add_material(audio_mat)
            audio_seg = AudioSegment(
                audio_mat,
                target_timerange=trange("0s", "3s"),
                source_timerange=trange("0s", "3s"),
            )
            script.add_segment(audio_seg, audio_track_name)
            print(f"  已添加音频素材: {os.path.basename(audio_path)}, 3秒")
            has_audio = True
            break

    if not has_audio:
        print("  (未找到测试音频，跳过)")

    # 添加文本轨道
    text_track_name = "文本轨道"
    script.add_track(TrackType.text, text_track_name)
    text_seg = TextSegment(
        "AI自动生成的测试草稿",
        trange("0s", "5s"),
        style=TextStyle(size=12, align=1, auto_wrapping=True),
        clip_settings=ClipSettings(transform_y=-0.7),
    )
    script.add_segment(text_seg, text_track_name)
    print("  已添加文本: 'AI自动生成的测试草稿'")

    # 保存
    script.save()
    print(f"\n  草稿已保存!")
    print(f"  路径: {script.save_path}")
    print(f"  总时长: {script.duration / 1_000_000:.1f}秒")

    # 验证保存的文件
    if os.path.exists(script.save_path):
        size = os.path.getsize(script.save_path)
        print(f"  文件大小: {size} bytes")

        # 检查是否JSON可读
        try:
            with open(script.save_path, 'r', encoding='utf-8') as f:
                saved = json.load(f)
            print(f"  JSON结构: 顶层keys={list(saved.keys())}")
            print(f"  tracks数: {len(saved.get('tracks', []))}")
            materials = saved.get('materials', {})
            print(f"  素材: videos={len(materials.get('videos', []))}, "
                  f"audios={len(materials.get('audios', []))}, "
                  f"texts={len(materials.get('texts', []))}")
        except:
            print("  (文件非JSON格式或已加密)")

    return script


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return

    cmd = sys.argv[1].lower()

    # ========================================
    # EXTRACT 模式
    # ========================================
    if cmd in ("extract", "demo"):
        print("=" * 60)
        print("剪映草稿素材提取工具")
        print("=" * 60)

        # 1. 找到最新草稿
        latest = find_latest_draft()
        if not latest:
            print("错误: 未找到草稿")
            return
        mtime, name, path = latest
        print(f"\n最新草稿: {name}")
        print(f"修改时间: {datetime.fromtimestamp(mtime)}")

        # 2. 检查草稿结构
        print("\n--- 草稿结构分析 ---")
        info = inspect_draft_structure(path)

        print(f"\n可读的JSON文件 ({len(info['readable_files'])}个):")
        for rel, data in info["readable_files"].items():
            if isinstance(data, dict):
                keys_str = ', '.join(list(data.keys())[:5])
                if len(data.keys()) > 5:
                    keys_str += f"... (+{len(data.keys()) - 5})"
                print(f"  {rel}")
                print(f"    keys: {keys_str}")
            else:
                print(f"  {rel} → {type(data).__name__}")

        print(f"\n加密/二进制文件 ({len(info['encrypted_files'])}个):")
        for f in info["encrypted_files"]:
            print(f"  {f}")

        # 3. 时间线信息
        if info.get("timeline_info"):
            tl = info["timeline_info"]
            print(f"\n--- 时间线信息 ---")
            print(f"  项目ID: {tl.get('id', 'N/A')}")
            print(f"  主时间线ID: {tl.get('main_timeline_id', 'N/A')}")
            if tl.get('timelines'):
                for t in tl['timelines']:
                    created = datetime.fromtimestamp(t['create_time'] / 1_000_000) if t.get('create_time') else 'N/A'
                    print(f"  时间线: {t.get('name', 'N/A')} (创建: {created})")

        # 4. 设置信息
        if info.get("settings"):
            print(f"\n--- 草稿设置 ---")
            print(info["settings"])

        # 5. 提取封面
        output_dir = os.path.dirname(os.path.abspath(__file__))
        cover = extract_cover(path, output_dir)
        if cover:
            print(f"\n封面图已提取: {cover}")

        # 6. 尝试 pyJianYingDraft API
        print(f"\n--- pyJianYingDraft API 测试 ---")
        folder = DraftFolder(DRAFT_DIR)

        # inspect_material
        print("\n[1] inspect_material:")
        try:
            folder.inspect_material(name)
            print("  成功!")
        except Exception as e:
            print(f"  失败 (预期，草稿已加密): {type(e).__name__}")

        # load_template
        print("\n[2] load_template:")
        try:
            script = folder.load_template(name)
            print(f"  成功! 导入轨道数: {len(script.imported_tracks)}")
        except Exception as e:
            print(f"  失败 (预期，草稿已加密): {type(e).__name__}")

        print("\n结论:")
        print("  你的剪映版本对 draft_content.json 进行了加密。")
        print("  pyJianYingDraft 的模板模式（提取素材）暂不支持加密草稿。")
        print("  但草稿生成模式（创建新草稿）不受影响。")

    # ========================================
    # REBUILD 模式
    # ========================================
    if cmd in ("rebuild", "demo"):
        print("\n" + "=" * 60)
        print("从零构建新草稿")
        print("=" * 60)
        create_test_draft()

    # ========================================
    # 完成提示
    # ========================================
    if cmd == "demo":
        print("\n" + "=" * 60)
        print("演示完成")
        print("=" * 60)
        print("""
下一步建议:
  1. 打开剪映 → 在草稿列表中找到 'AI_Test_Rebuild'
  2. 检查草稿是否能正常打开
  3. 如果打不开，说明剪映版本与 pyJianYingDraft 模板不兼容
     需要更新模板的 version/app_version 字段
""")


if __name__ == "__main__":
    main()
