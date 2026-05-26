"""应用日志：文件写入 + 内存缓存 + API 查询"""
import os
import time
import json
import traceback
from datetime import datetime
from threading import Lock

LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs")
os.makedirs(LOG_DIR, exist_ok=True)

_lock = Lock()
_buffer: list = []  # 最近 200 条
MAX_BUFFER = 200


def _write_log(level: str, msg: str, detail: str = ""):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] [{level}] {msg}"
    if detail:
        line += f"\n  {detail}"

    # 写文件
    today = datetime.now().strftime("%Y-%m-%d")
    log_path = os.path.join(LOG_DIR, f"{today}.log")
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(line + "\n")

    # 内存缓存
    with _lock:
        _buffer.append({"time": ts, "level": level, "msg": msg, "detail": detail})
        if len(_buffer) > MAX_BUFFER:
            _buffer.pop(0)


def info(msg: str, detail: str = ""):
    _write_log("INFO", msg, detail)


def error(msg: str, detail: str = ""):
    _write_log("ERROR", msg, detail)


def api_error(endpoint: str, method: str, error_msg: str, body: str = ""):
    msg = f"{method} {endpoint}"
    detail = f"Error: {error_msg}"
    if body:
        detail += f"\nBody: {body[:500]}"
    _write_log("API_ERROR", msg, detail)


def api_ok(endpoint: str, method: str, status: int = 200):
    _write_log("API_OK", f"{method} {endpoint} → {status}")


def get_recent(limit: int = 50, level: str = "") -> list:
    """获取最近 N 条日志，可按级别筛选"""
    with _lock:
        logs = list(_buffer)
    if level:
        logs = [l for l in logs if l["level"] == level]
    return logs[-limit:]


def get_log_files() -> list:
    """列出所有日志文件"""
    files = []
    for f in sorted(os.listdir(LOG_DIR), reverse=True):
        if f.endswith(".log"):
            path = os.path.join(LOG_DIR, f)
            files.append({"name": f, "size": os.path.getsize(path)})
    return files[:30]


def read_log_file(filename: str, tail: int = 200) -> str:
    """读取指定日志文件的最后 N 行"""
    path = os.path.join(LOG_DIR, filename)
    if not os.path.exists(path):
        return ""
    with open(path, "r", encoding="utf-8") as f:
        lines = f.readlines()
    return "".join(lines[-tail:])
