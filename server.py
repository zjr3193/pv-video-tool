"""光伏短视频工具 — FastAPI 主服务"""
import os
import sys
import json
import shutil
import asyncio
from datetime import datetime
from typing import Optional
from concurrent.futures import ThreadPoolExecutor

from fastapi import FastAPI, File, UploadFile, Form, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

sys.path.insert(0, os.path.dirname(__file__))
from services import project as proj
from services.api_client import (
    analyze_vision, generate_anchor_prompt, generate_narration,
    generate_image_from_text, generate_image_from_ref,
    synthesize_tts, get_audio_duration_ms,
)
from services.jianying_draft import build_draft as jy_build_draft

app = FastAPI(title="光伏短视频工具")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


class NoCacheMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        return response

app.add_middleware(NoCacheMiddleware)

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# 静态文件
app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/output", StaticFiles(directory=OUTPUT_DIR), name="output")

# 线程池用于异步任务
executor = ThreadPoolExecutor(max_workers=4)


# ============================================
# 首页
# ============================================
@app.get("/")
def serve_index():
    return FileResponse("static/index.html")


# ============================================
# 项目管理
# ============================================
@app.get("/api/projects")
def api_list_projects():
    return JSONResponse(proj.list_projects())


@app.post("/api/projects")
def api_create_project():
    name = proj.generate_project_name()
    data = proj.create_project(name)
    return JSONResponse({"success": True, "name": name, "data": data})


@app.get("/api/projects/{name}")
def api_get_project(name: str):
    data = proj.load_project(name)
    if data is None:
        raise HTTPException(404, "项目不存在")
    return JSONResponse(data)


@app.delete("/api/projects/{name}")
def api_delete_project(name: str):
    proj.delete_project(name)
    return JSONResponse({"success": True})


# ============================================
# 步骤 1：上传源图
# ============================================
@app.post("/api/projects/{name}/upload-source")
async def api_upload_source(name: str, file: UploadFile = File(...)):
    data = proj.load_project(name)
    if data is None:
        raise HTTPException(404, "项目不存在")

    # 校验格式
    ext = os.path.splitext(file.filename or "image.jpg")[1].lower()
    if ext not in (".jpg", ".jpeg", ".png", ".webp"):
        raise HTTPException(400, "仅支持 JPG、PNG、WEBP 格式")

    # 保存前先废弃旧图
    if data.get("source_image"):
        proj.move_to_discarded(name, os.path.basename(data["source_image"]))

    save_path = os.path.join(OUTPUT_DIR, name, "images", f"source{ext}")
    with open(save_path, "wb") as f:
        f.write(await file.read())

    data["source_image"] = f"images/source{ext}"
    data["status"] = "source_uploaded"
    proj.save_project(name, data)

    return JSONResponse({"success": True, "path": data["source_image"]})


# ============================================
# 步骤 2：识图分析
# ============================================
@app.post("/api/projects/{name}/analyze-vision")
def api_analyze_vision(name: str):
    data = proj.load_project(name)
    if data is None:
        raise HTTPException(404, "项目不存在")
    if not data.get("source_image"):
        raise HTTPException(400, "请先上传源图")

    img_path = os.path.join(OUTPUT_DIR, name, data["source_image"])
    if not os.path.exists(img_path):
        raise HTTPException(400, "源图文件不存在")

    try:
        result = analyze_vision(img_path)
        data["vision_result"] = result
        data["status"] = "vision_done"
        proj.save_project(name, data)
        return JSONResponse({"success": True, "result": result})
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, 500)


# ============================================
# 步骤 3：Agent 生成提示词
# ============================================
@app.post("/api/projects/{name}/generate-prompt")
def api_generate_prompt(name: str):
    data = proj.load_project(name)
    if data is None:
        raise HTTPException(404, "项目不存在")
    vision = data.get("vision_result")
    if not vision:
        raise HTTPException(400, "请先完成识图分析")

    try:
        result = generate_anchor_prompt(vision)
        data["anchor_prompt"] = result
        data["status"] = "prompt_done"
        proj.save_project(name, data)
        return JSONResponse({"success": True, "result": result})
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, 500)


# ============================================
# 步骤 4：生成锚图
# ============================================
@app.post("/api/projects/{name}/generate-anchor")
def api_generate_anchor(name: str):
    data = proj.load_project(name)
    if data is None:
        raise HTTPException(404, "项目不存在")
    prompt = data.get("anchor_prompt", {})
    en_prompt = prompt.get("en_prompt", "") if isinstance(prompt, dict) else str(prompt)
    if not en_prompt:
        raise HTTPException(400, "请先生成提示词")

    # 废弃旧锚图
    if data.get("anchor_image"):
        proj.move_to_discarded(name, os.path.basename(data["anchor_image"]))

    save_path = os.path.join(OUTPUT_DIR, name, "images", "anchor.png")
    result = generate_image_from_text(en_prompt, save_path)

    if result.get("success"):
        data["anchor_image"] = "images/anchor.png"
        data["status"] = "anchor_done"
        proj.save_project(name, data)
        return JSONResponse({"success": True, "path": data["anchor_image"]})
    return JSONResponse({"success": False, "error": result.get("error", "锚图生成失败")}, 500)


# ============================================
# 步骤 5：批量生成套图
# ============================================
@app.post("/api/projects/{name}/generate-set")
async def api_generate_set(name: str):
    data = proj.load_project(name)
    if data is None:
        raise HTTPException(404, "项目不存在")
    if not data.get("anchor_image"):
        raise HTTPException(400, "请先生成锚图")

    anchor_path = os.path.join(OUTPUT_DIR, name, data["anchor_image"])
    if not os.path.exists(anchor_path):
        raise HTTPException(400, "锚图文件不存在")

    # 筛选待生成的套图（pending 或 failed 状态）
    pending = [img for img in data["set_images"]
               if not img.get("is_custom") and img["status"] in ("pending", "failed")]
    if not pending:
        return JSONResponse({"success": True, "message": "没有待生成的套图"})

    # 更新状态
    for img in pending:
        img["status"] = "generating"
    proj.save_project(name, data)

    # 并行生成（最多 4 路并发）
    sem = asyncio.Semaphore(4)

    async def gen_one(img):
        async with sem:
            sid = img["id"]
            ratio = img["aspect_ratio"]
            save_name = f"{sid}_{ratio.replace(':', 'x')}.png"
            save_path = os.path.join(OUTPUT_DIR, name, "images", save_name)

            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                executor,
                generate_image_from_ref,
                anchor_path, img["prompt_diff"], save_path, ratio
            )

            # 重新加载数据
            cur = proj.load_project(name)
            success_flag = result.get("success")
            for s in cur["set_images"]:
                if s["id"] == sid:
                    if success_flag:
                        if s.get("generated_image"):
                            proj.move_to_discarded(name, os.path.basename(s["generated_image"]))
                        s["status"] = "done"
                        s["generated_image"] = f"images/{save_name}"
                    else:
                        s["status"] = "failed"
                        s["error_msg"] = result.get("error", "未知错误")
                    break
            proj.save_project(name, cur)
            return {"id": sid, "success": success_flag, "error": result.get("error")}

    results = await asyncio.gather(*[gen_one(img) for img in pending])

    # 更新项目状态
    data = proj.load_project(name)
    if all(img["status"] == "done" for img in data["set_images"] if not img.get("is_custom")):
        data["status"] = "set_done"
    proj.save_project(name, data)

    return JSONResponse({"success": True, "results": results})


# ============================================
# 单张套图重新生成
# ============================================
@app.post("/api/projects/{name}/regenerate-set/{set_id}")
async def api_regenerate_set(name: str, set_id: str):
    data = proj.load_project(name)
    if data is None:
        raise HTTPException(404, "项目不存在")
    if not data.get("anchor_image"):
        raise HTTPException(400, "请先生成锚图")

    img = next((s for s in data["set_images"] if s["id"] == set_id), None)
    if img is None:
        raise HTTPException(404, "套图不存在")

    anchor_path = os.path.join(OUTPUT_DIR, name, data["anchor_image"])

    # 废弃旧图
    if img.get("generated_image"):
        proj.move_to_discarded(name, os.path.basename(img["generated_image"]))

    img["status"] = "generating"
    proj.save_project(name, data)

    ratio = img["aspect_ratio"]
    save_name = f"{set_id}_{ratio.replace(':', 'x')}.png"
    save_path = os.path.join(OUTPUT_DIR, name, "images", save_name)

    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(
        executor,
        generate_image_from_ref,
        anchor_path, img["prompt_diff"], save_path, ratio
    )

    data = proj.load_project(name)
    for s in data["set_images"]:
        if s["id"] == set_id:
            s["status"] = "done" if result.get("success") else "failed"
            if result.get("success"):
                s["generated_image"] = f"images/{save_name}"
                s["error_msg"] = ""
            else:
                s["error_msg"] = result.get("error", "未知错误")
            break
    proj.save_project(name, data)

    return JSONResponse({"success": success})


# ============================================
# 步骤 6+7：批量口播生成 + TTS
# ============================================
@app.post("/api/projects/{name}/generate-narrations")
async def api_generate_narrations(name: str):
    data = proj.load_project(name)
    if data is None:
        raise HTTPException(404, "项目不存在")

    pending = [img for img in data["set_images"]
               if img["status"] == "done" and not img.get("narration")]
    if not pending:
        return JSONResponse({"success": True, "message": "没有需要生成口播的套图"})

    sem = asyncio.Semaphore(4)
    vision = data.get("vision_result", "")

    async def gen_one(img):
        async with sem:
            loop = asyncio.get_event_loop()
            narr = await loop.run_in_executor(
                executor, generate_narration,
                img["scene"], img["view_angle"], vision
            )
            cur = proj.load_project(name)
            for s in cur["set_images"]:
                if s["id"] == img["id"]:
                    s["narration"] = narr
                    break
            proj.save_project(name, cur)
            return {"id": img["id"], "narration": narr}

    results = await asyncio.gather(*[gen_one(img) for img in pending])
    data = proj.load_project(name)
    data["status"] = "narration_done" if any(
        img.get("narration") for img in data["set_images"]
    ) else data["status"]
    proj.save_project(name, data)

    return JSONResponse({"success": True, "results": results})


# ============================================
# 步骤 7：TTS 语音合成
# ============================================
@app.post("/api/projects/{name}/synthesize-tts")
async def api_synthesize_tts(name: str):
    data = proj.load_project(name)
    if data is None:
        raise HTTPException(404, "项目不存在")

    pending = [img for img in data["set_images"]
               if img.get("narration") and not img.get("narration_audio")]
    if not pending:
        return JSONResponse({"success": True, "message": "没有需要合成的语音"})

    async def syn_one(img):
        sid = img["id"]
        save_path = os.path.join(OUTPUT_DIR, name, "audio", f"{sid}.mp3")

        loop = asyncio.get_event_loop()
        success = await loop.run_in_executor(
            executor, synthesize_tts, img["narration"], save_path
        )

        cur = proj.load_project(name)
        for s in cur["set_images"]:
            if s["id"] == sid and success:
                s["narration_audio"] = f"audio/{sid}.mp3"
                s["audio_duration"] = get_audio_duration_ms(save_path)
                break
        proj.save_project(name, cur)
        return {"id": sid, "success": success}

    results = await asyncio.gather(*[syn_one(img) for img in pending])
    return JSONResponse({"success": True, "results": results})


# ============================================
# 更新套图 显示文字/口播内容
# ============================================
@app.put("/api/projects/{name}/set-images/{set_id}")
def api_update_set_image(name: str, set_id: str, body: dict):
    data = proj.load_project(name)
    if data is None:
        raise HTTPException(404, "项目不存在")

    for img in data["set_images"]:
        if img["id"] == set_id:
            if "display_text" in body:
                img["display_text"] = body["display_text"][:20]
            if "narration" in body:
                img["narration"] = body["narration"]
            if "aspect_ratio" in body:
                img["aspect_ratio"] = body["aspect_ratio"]
            break

    proj.save_project(name, data)
    return JSONResponse({"success": True})


# ============================================
# 新增自定义套图
# ============================================
@app.post("/api/projects/{name}/custom-image")
async def api_add_custom_image(name: str, file: UploadFile = File(...),
                               scene: str = Form(...), aspect_ratio: str = Form("16:9")):
    data = proj.load_project(name)
    if data is None:
        raise HTTPException(404, "项目不存在")

    ext = os.path.splitext(file.filename or "custom.jpg")[1].lower()
    if ext not in (".jpg", ".jpeg", ".png", ".webp"):
        raise HTTPException(400, "仅支持 JPG、PNG、WEBP 格式")

    # 生成 ID
    customs = [img for img in data["set_images"] if img.get("is_custom")]
    custom_id = f"custom_{len(customs) + 1:02d}"
    while any(img["id"] == custom_id for img in data["set_images"]):
        from random import randint
        custom_id = f"custom_{len(customs) + 1:02d}_{randint(1000, 9999)}"

    max_order = max((img["order"] for img in data["set_images"]), default=12)

    save_name = f"{custom_id}.png"
    save_path = os.path.join(OUTPUT_DIR, name, "images", save_name)
    with open(save_path, "wb") as f:
        f.write(await file.read())

    data["set_images"].append({
        "id": custom_id,
        "is_custom": True,
        "aspect_ratio": aspect_ratio,
        "view_angle": "custom",
        "scene": scene,
        "prompt_diff": "",
        "order": max_order + 1,
        "custom_image": f"images/{save_name}",
        "generated_image": None,
        "display_text": "",
        "narration": "",
        "narration_audio": None,
        "audio_duration": 0,
        "status": "done",
    })

    proj.save_project(name, data)
    return JSONResponse({"success": True, "id": custom_id})


# ============================================
# 上传背景音乐
# ============================================
@app.post("/api/projects/{name}/upload-bgm")
async def api_upload_bgm(name: str, file: UploadFile = File(...)):
    data = proj.load_project(name)
    if data is None:
        raise HTTPException(404, "项目不存在")

    ext = os.path.splitext(file.filename or "bgm.mp3")[1].lower()
    if ext not in (".mp3", ".wav", ".m4a", ".aac"):
        raise HTTPException(400, "仅支持 MP3、WAV、M4A、AAC 格式")

    save_name = f"bgm{ext}"
    save_path = os.path.join(OUTPUT_DIR, name, "audio", save_name)
    with open(save_path, "wb") as f:
        f.write(await file.read())

    data["bgm_path"] = f"audio/{save_name}"
    proj.save_project(name, data)
    return JSONResponse({"success": True, "path": data["bgm_path"]})


# ============================================
# 步骤 8：构建剪映草稿
# ============================================
@app.post("/api/projects/{name}/build-draft")
def api_build_draft(name: str, body: dict):
    data = proj.load_project(name)
    if data is None:
        raise HTTPException(404, "项目不存在")

    aspect = body.get("aspect_ratio", "16:9")
    draft_name = body.get("draft_name", f"{name}_{aspect.replace(':', 'x')}")

    result = jy_build_draft(name, data, aspect, draft_name)
    if result.get("success"):
        data["status"] = "draft_done"
        proj.save_project(name, data)

    return JSONResponse(result)


# ============================================
# 启动
# ============================================
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8765)
