"""SuperMOA — 系统托盘程序

双击运行此文件即启动托盘 + 后台 FastAPI 服务。
"""
import os
import sys
import threading
import webbrowser
import subprocess
import socket
import time
import logging
from pathlib import Path

# 把项目根目录加入 sys.path（PyInstaller 打包后不需要）
if not getattr(sys, "frozen", False):
    sys.path.insert(0, str(Path(__file__).parent.resolve()))

import pystray
from PIL import Image, ImageDraw, ImageFont
import uvicorn

from app import app
from engine.config import load_config, ensure_config, get_config_path
from engine.auth import ensure_api_key, get_current_key, regenerate_api_key, mask_key

logger = logging.getLogger("supermoa")


# ============================================================
# 服务管理（子线程跑 uvicorn）
# ============================================================
_server_lock = threading.Lock()
_server: uvicorn.Server = None
_server_thread: threading.Thread = None


def is_running() -> bool:
    return _server is not None and not _server.should_exit


def start_server():
    global _server, _server_thread
    with _server_lock:
        if is_running():
            return False, "服务已在运行"
        try:
            config = load_config()
            host = config["gateway"].get("host", "127.0.0.1")
            port = config["gateway"].get("port", 12345)

            uv_config = uvicorn.Config(
                app, host=host, port=port,
                log_level="warning", access_log=False,
            )
            _server = uvicorn.Server(uv_config)
            _server_thread = threading.Thread(target=_server.run, daemon=True)
            _server_thread.start()
            return True, f"服务已启动: http://{host}:{port}"
        except Exception as e:
            _server = None
            return False, f"启动失败: {type(e).__name__}: {e}"


def _is_port_in_use(host: str, port: int) -> bool:
    """检查端口是否被占用"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex((host, port)) == 0


def _wait_for_port_release(host: str, port: int, timeout: float = 5.0) -> bool:
    """等待端口释放，最多等 timeout 秒。返回 True 表示端口已释放。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if not _is_port_in_use(host, port):
            return True
        time.sleep(0.2)
    return not _is_port_in_use(host, port)


def stop_server():
    """停止服务并等待线程退出，避免端口残留"""
    global _server, _server_thread
    with _server_lock:
        if _server is None:
            return False, "服务未运行"
        _server.should_exit = True
        server_thread = _server_thread
        _server = None
        _server_thread = None
    # 在锁外等待旧线程退出，避免长时间持锁
    if server_thread is not None and server_thread.is_alive():
        server_thread.join(timeout=5.0)
        if server_thread.is_alive():
            logger.warning("服务线程未在 5 秒内退出，可能存在端口残留")
    return True, "服务已停止"


def restart_server():
    """重启服务：停止 → 等待端口释放 → 启动"""
    stopped, _ = stop_server()
    if not stopped:
        # 服务未运行，直接启动
        return start_server()
    # 探测端口是否已释放，最多等 5 秒
    config = load_config()
    host = config["gateway"].get("host", "127.0.0.1")
    port = config["gateway"].get("port", 12345)
    if not _wait_for_port_release(host, port, timeout=5.0):
        return False, f"端口 {port} 未在 5 秒内释放，重启失败"
    return start_server()


# ============================================================
# 托盘图标
# ============================================================
def create_icon_image() -> Image.Image:
    """生成一个简单的 M 字母图标"""
    img = Image.new("RGB", (64, 64), "#2563eb")
    draw = ImageDraw.Draw(img)
    try:
        # Windows 默认字体
        font = ImageFont.truetype("arial.ttf", 42)
    except (OSError, IOError):
        font = ImageFont.load_default()
    # 居中画 M
    bbox = draw.textbbox((0, 0), "M", font=font)
    w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text(((64 - w) / 2 - bbox[0], (64 - h) / 2 - bbox[1]), "M", fill="white", font=font)
    return img


# ============================================================
# 菜单回调
# ============================================================
def on_start(icon, item):
    ok, msg = start_server()
    _notify(icon, "SuperMOA", msg)


def on_stop(icon, item):
    ok, msg = stop_server()
    _notify(icon, "SuperMOA", msg)


def on_restart(icon, item):
    ok, msg = restart_server()
    _notify(icon, "SuperMOA", msg)


def on_open_web(icon, item):
    config = load_config()
    host = config["gateway"].get("host", "127.0.0.1")
    port = config["gateway"].get("port", 12345)
    url = f"http://{host}:{port}/"
    webbrowser.open(url)


def on_copy_key(icon, item):
    """复制 API Key 到剪贴板（Windows: clip 命令）"""
    key = get_current_key()
    if not key:
        _notify(icon, "SuperMOA", "未找到 API Key")
        return
    try:
        if sys.platform == "win32":
            process = subprocess.Popen(["clip"], stdin=subprocess.PIPE)
            process.communicate(key.encode("utf-8"))
        else:
            # macOS / Linux
            try:
                process = subprocess.Popen(["pbcopy"], stdin=subprocess.PIPE)
                process.communicate(key.encode("utf-8"))
            except (FileNotFoundError, OSError):
                process = subprocess.Popen(["xclip", "-selection", "clipboard"], stdin=subprocess.PIPE)
                process.communicate(key.encode("utf-8"))
        _notify(icon, "SuperMOA", f"Key 已复制: {mask_key(key)}")
    except Exception as e:
        _notify(icon, "SuperMOA", f"复制失败: {e}")


def on_show_key(icon, item):
    key = get_current_key()
    _notify(icon, "SuperMOA — API Key", key or "未生成")


def on_regen_key(icon, item):
    """重新生成 Key（直接生成，不再弹原生确认框——托盘环境难做对话框）"""
    new_key = regenerate_api_key()
    _notify(icon, "SuperMOA", f"新 Key 已生成: {mask_key(new_key)}\n请更新智能体配置")


def on_exit(icon, item):
    stop_server()
    icon.stop()


def _notify(icon, title, msg):
    """托盘通知（Windows 用 INFO 针）"""
    try:
        icon.notify(msg, title)
    except Exception as e:
        import logging
        logging.getLogger("supermoa").warning("托盘通知失败: %s", str(e)[:100])


# ============================================================
# 菜单
# ============================================================
def build_menu() -> pystray.Menu:
    return pystray.Menu(
        pystray.MenuItem(
            "启动服务",
            on_start,
            visible=lambda item: not is_running(),
        ),
        pystray.MenuItem(
            "停止服务",
            on_stop,
            visible=lambda item: is_running(),
        ),
        pystray.MenuItem("重启服务", on_restart),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("打开配置页", on_open_web),
        pystray.MenuItem("显示 API Key", on_show_key),
        pystray.MenuItem("复制 API Key", on_copy_key),
        pystray.MenuItem("重新生成 Key", on_regen_key),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("退出", on_exit),
    )


# ============================================================
# 入口
# ============================================================
def main():
    # 确保配置 + Key 已生成
    ensure_config()
    ensure_api_key()

    # 自动启动服务
    start_server()

    # 启动托盘
    icon = pystray.Icon(
        "supermoa",
        icon=create_icon_image(),
        title="SuperMOA",
        menu=build_menu(),
    )
    icon.run()


if __name__ == "__main__":
    main()
