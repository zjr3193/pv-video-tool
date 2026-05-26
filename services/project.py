"""项目管理：JSON 文件读写，项目 CRUD"""
import os
import json
import shutil
from datetime import datetime
from typing import Optional

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "output")


def ensure_output_dir():
    os.makedirs(OUTPUT_DIR, exist_ok=True)


def list_projects() -> list:
    """列出所有项目"""
    ensure_output_dir()
    projects = []
    for name in os.listdir(OUTPUT_DIR):
        proj_path = os.path.join(OUTPUT_DIR, name)
        if os.path.isdir(proj_path) and not name.startswith('.'):
            info = load_project(name)
            projects.append({
                "name": name,
                "path": proj_path,
                "status": info.get("status", "new") if info else "new",
                "created_at": info.get("created_at", "") if info else "",
                "source_thumbnail": _get_thumbnail(info),
            })
    projects.sort(key=lambda p: p["name"], reverse=True)
    return projects


def _get_thumbnail(info: dict) -> Optional[str]:
    """获取项目缩略图路径"""
    if not info:
        return None
    source = info.get("source_image")
    if source:
        full = os.path.join(OUTPUT_DIR, info.get("name", ""), source)
        if os.path.exists(full):
            return f"/output/{info['name']}/{source}"
    anchor = info.get("anchor_image")
    if anchor:
        full = os.path.join(OUTPUT_DIR, info.get("name", ""), anchor)
        if os.path.exists(full):
            return f"/output/{info['name']}/{anchor}"
    return None


def create_project(name: str) -> dict:
    """创建新项目"""
    proj_dir = os.path.join(OUTPUT_DIR, name)
    if os.path.exists(proj_dir):
        raise FileExistsError(f"项目 {name} 已存在")

    os.makedirs(os.path.join(proj_dir, "images", "discarded"), exist_ok=True)
    os.makedirs(os.path.join(proj_dir, "audio"), exist_ok=True)

    info = {
        "name": name,
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "status": "new",
        "source_image": None,
        "vision_result": None,
        "anchor_prompt": None,
        "anchor_image": None,
        "set_images": _default_set_images(),
        "bgm_path": None,
    }
    _save_project(name, info)
    return info


def _default_set_images() -> list:
    """生成默认 12 张套图配置"""
    configs = [
        ("set_01", "16:9", "eye_level", "厂房正门", "Front entrance of the same factory building, eye-level view"),
        ("set_02", "16:9", "drone", "未安装-厂房屋顶", "Drone aerial view directly above the same factory rooftop, roof is clean and empty, no solar panels"),
        ("set_03", "16:9", "drone", "安装中-工人在安装支架", "Drone aerial view, workers on the rooftop installing solar panel mounting brackets"),
        ("set_04", "16:9", "drone", "安装中-吊车吊组件", "Drone aerial view, crane lifting solar panel components, workers installing on same rooftop"),
        ("set_05", "16:9", "drone", "安装后-厂房屋顶", "Drone aerial view, same rooftop fully covered with solar panels"),
        ("set_06", "16:9", "drone", "安装前中后对比", "Three-panel split: before (empty roof), during (installation), after (full solar panels) of the same factory"),
        ("set_07", "9:16", "eye_level", "厂房正门", "Front entrance of the same factory building, eye-level view, vertical 9:16"),
        ("set_08", "9:16", "drone", "未安装-厂房屋顶", "Drone view, same empty rooftop, vertical 9:16"),
        ("set_09", "9:16", "drone", "安装中-工人在安装支架", "Drone view, workers installing brackets, vertical 9:16"),
        ("set_10", "9:16", "drone", "安装中-吊车吊组件", "Drone view, crane and workers, vertical 9:16"),
        ("set_11", "9:16", "drone", "安装后-厂房屋顶", "Drone view, rooftop with solar panels, vertical 9:16"),
        ("set_12", "9:16", "drone", "安装前中后对比", "Three-panel split, same factory, vertical 9:16"),
    ]
    images = []
    for i, (sid, ratio, angle, scene, prompt_diff) in enumerate(configs):
        images.append({
            "id": sid, "aspect_ratio": ratio, "view_angle": angle,
            "scene": scene, "prompt_diff": prompt_diff, "order": i + 1,
            "is_custom": False,
            "generated_image": None, "display_text": "", "narration": "",
            "narration_audio": None, "audio_duration": 0,
            "status": "pending",
        })
    return images


def load_project(name: str) -> Optional[dict]:
    """加载项目数据"""
    path = os.path.join(OUTPUT_DIR, name, "project.json")
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_project(name: str, data: dict):
    """保存项目数据"""
    data["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    _save_project(name, data)


def _save_project(name: str, data: dict):
    path = os.path.join(OUTPUT_DIR, name, "project.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def delete_project(name: str):
    """删除整个项目目录"""
    proj_dir = os.path.join(OUTPUT_DIR, name)
    if os.path.exists(proj_dir):
        shutil.rmtree(proj_dir)


def generate_project_name() -> str:
    """生成项目名称：日期 或 日期-序号"""
    today = datetime.now().strftime("%Y-%m-%d")
    ensure_output_dir()
    existing = [d for d in os.listdir(OUTPUT_DIR) if d.startswith(today)]
    if not existing:
        return today
    nums = []
    for e in existing:
        parts = e.split("-")
        if len(parts) >= 4 and parts[-1].isdigit():
            nums.append(int(parts[-1]))
    if not nums:
        return f"{today}-2"
    return f"{today}-{max(nums) + 1}"


def move_to_discarded(proj_name: str, filename: str):
    """将文件移至 discarded 目录"""
    src = os.path.join(OUTPUT_DIR, proj_name, "images", filename)
    if not os.path.exists(src):
        return
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    name, ext = os.path.splitext(filename)
    dst = os.path.join(OUTPUT_DIR, proj_name, "images", "discarded", f"{name}_{ts}{ext}")
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    shutil.move(src, dst)
