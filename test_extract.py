"""
测试脚本：从剪映最新草稿中提取素材信息，并尝试重构新草稿
"""
import pyJianYingDraft as draft
import os
import json

DRAFT_DIR = r"E:\JianyingPro Drafts"
LATEST_DRAFT = "5月25日 (1)"

def main():
    print("=" * 60)
    print("1. 初始化 DraftFolder")
    print("=" * 60)
    folder = draft.DraftFolder(DRAFT_DIR)

    # 列出所有草稿
    print(f"\n草稿目录: {DRAFT_DIR}")
    print(f"最新草稿: {LATEST_DRAFT}")

    # ==========================================
    # Step 1: 尝试 inspect_material (提取素材元数据)
    # ==========================================
    print("\n" + "=" * 60)
    print("2. 尝试 inspect_material —— 提取贴纸/花字元数据")
    print("=" * 60)
    try:
        folder.inspect_material(LATEST_DRAFT)
        print("  ✓ inspect_material 成功")
    except Exception as e:
        print(f"  ✗ inspect_material 失败: {e}")

    # ==========================================
    # Step 2: 尝试 load_template (加载草稿为模板)
    # ==========================================
    print("\n" + "=" * 60)
    print("3. 尝试 load_template —— 加载加密草稿")
    print("=" * 60)
    try:
        script = folder.load_template(LATEST_DRAFT)
        print(f"  ✓ load_template 成功, type={type(script)}")
    except Exception as e:
        print(f"  ✗ load_template 失败: {e}")
        script = None

    # ==========================================
    # Step 3: 尝试 duplicate_as_template
    # ==========================================
    print("\n" + "=" * 60)
    print("4. 尝试 duplicate_as_template —— 复制草稿为模板")
    print("=" * 60)
    try:
        script2 = folder.duplicate_as_template(LATEST_DRAFT, "测试_提取重建")
        print(f"  ✓ duplicate_as_template 成功")
        script = script2
    except Exception as e:
        print(f"  ✗ duplicate_as_template 失败: {e}")

    # ==========================================
    # Step 4: 检查可读文件
    # ==========================================
    print("\n" + "=" * 60)
    print("5. 检查草稿中的可读 JSON 文件")
    print("=" * 60)
    draft_path = os.path.join(DRAFT_DIR, LATEST_DRAFT)
    readable_files = []
    for root, dirs, files in os.walk(draft_path):
        for f in files:
            fpath = os.path.join(root, f)
            if f.endswith('.json') and not f.endswith('.bak'):
                try:
                    with open(fpath, 'r', encoding='utf-8') as fh:
                        data = json.load(fh)
                    size = os.path.getsize(fpath)
                    rel = os.path.relpath(fpath, draft_path)
                    readable_files.append((rel, size, type(data).__name__, list(data.keys()) if isinstance(data, dict) else 'list'))
                except:
                    pass

    for rel, size, dtype, keys in readable_files:
        print(f"  {rel} ({size}B) → {dtype}, keys={keys}")

    # ==========================================
    # Step 5: 尝试直接用 Script 从头构建一个草稿
    # ==========================================
    print("\n" + "=" * 60)
    print("6. 尝试用 API 从头构建一个测试草稿")
    print("=" * 60)
    try:
        new_script = draft.ScriptFile(
            width=1080, height=1920, fps=30,
            duration=draft.trange("0s", "10s").duration()
        )
        print(f"  ✓ ScriptFile 创建成功")
        print(f"    画布: {new_script.width}x{new_script.height}")
        print(f"    FPS: {new_script.fps}")
    except Exception as e:
        print(f"  ✗ ScriptFile 创建失败: {e}")

    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)


if __name__ == "__main__":
    main()
