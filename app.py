"""SuperMOA — FastAPI 应用创建 + 生命周期管理

职责：
- 创建 FastAPI app 实例
- startup：初始化日志、用量统计、健康检查、httpx 连接池
- shutdown：关闭健康检查、httpx 连接池
- 注册路由（chat + admin）
- run_server 入口
"""
import logging
import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse

from engine.auth import ensure_api_key, get_current_key, mask_key
from engine.config import load_config, ensure_config, get_config_path
from engine import health as health_module
from engine import constants as C
from engine.log_manager import init_log_manager, get_log_manager
from engine.http_client import close_client
from engine.usage import init_usage_db
from engine import error_reporter

logger = logging.getLogger("supermoa")

# ============================================================
# 路径处理（兼容 PyInstaller 打包）
# ============================================================
if getattr(sys, "frozen", False):
    BASE_DIR = Path(sys._MEIPASS)
else:
    BASE_DIR = Path(__file__).parent.resolve()
WEB_DIR = BASE_DIR / "web"

# ============================================================
# FastAPI app 创建
# ============================================================
app = FastAPI(title="SuperMOA", version="1.0.0")

# 请求日志管理器
_log_mgr = get_log_manager()


def _identify_client(user_agent: str, model_field: str) -> str:
    """根据 User-Agent 识别调用来源"""
    ua = (user_agent or "").lower()
    if "workbuddy" in ua or "codebuddy" in ua:
        return "WorkBuddy"
    if "hermes" in ua:
        return "Hermes"
    if "cursor" in ua:
        return "Cursor"
    if "claude" in ua or "anthropic" in ua:
        return "Claude Code"
    if "python" in ua and "httpx" in ua:
        return "Python/httpx"
    if "node" in ua or "axios" in ua:
        return "Node.js"
    if "mozilla" in ua or "chrome" in ua:
        return "浏览器"
    if "openai" in ua:
        return "Hermes"
    return ua[:20] if ua else "Unknown"


def _log_request(model_field: str, route: str, actual_model: str, prefix: str, prompt_preview: str, client: str = "", is_user_message: bool = False):
    """记录一条请求日志（通过 LogManager，含去重+轮转逻辑）"""
    _log_mgr.log_request(model_field, route, actual_model, prefix, prompt_preview, client, is_user_message)


# ============================================================
# 配置 mask/unmask 工具
# ============================================================
def _mask_config(config: dict) -> dict:
    """把 config 中的 api_key 替换为 mask 格式"""
    import copy
    masked = copy.deepcopy(config)

    for ref in masked.get("reference_models") or []:
        if ref.get("api_key"):
            ref["api_key"] = mask_key(ref["api_key"])
    agg = masked.get("aggregator") or {}
    if agg.get("api_key"):
        agg["api_key"] = mask_key(agg["api_key"])
    dp = masked.get("default_passthrough") or {}
    if dp.get("api_key"):
        dp["api_key"] = mask_key(dp["api_key"])
    return masked


def _unmask_config(submitted: dict, current: dict) -> dict:
    """如果提交的 api_key 是 mask 格式（含 ...），用 current 里的真实 key 替换"""
    import copy
    result = copy.deepcopy(submitted)

    def _restore(sub_list, cur_list, key_name="model"):
        cur_map = {c.get(key_name): c for c in (cur_list or []) if c.get(key_name)}
        for item in sub_list or []:
            name = item.get(key_name)
            cur_item = cur_map.get(name)
            if cur_item and item.get("api_key", "").find("...") >= 0:
                item["api_key"] = cur_item.get("api_key", "")

    _restore(result.get("reference_models"), current.get("reference_models"))
    agg_sub = result.get("aggregator") or {}
    if agg_sub.get("api_key", "").find("...") >= 0:
        cur_agg = current.get("aggregator") or {}
        agg_sub["api_key"] = cur_agg.get("api_key", "")
    dp_sub = result.get("default_passthrough") or {}
    if dp_sub.get("api_key", "").find("...") >= 0:
        cur_dp = current.get("default_passthrough") or {}
        dp_sub["api_key"] = cur_dp.get("api_key", "")
    return result


# ============================================================
# 生命周期事件
# ============================================================
@app.on_event("startup")
async def startup_event():
    """启动时：初始化日志 + 用量统计 + 错误上报 + 启动后台健康检查"""
    try:
        from engine.config import CONFIG_DIR
        log_file = CONFIG_DIR / "logs.jsonl"
        init_log_manager(log_file)
    except (IOError, OSError, ValueError) as e:
        logger.warning("日志初始化失败: %s", str(e)[:100])
    try:
        from engine.config import CONFIG_DIR
        init_usage_db(CONFIG_DIR)
    except Exception as e:
        logger.warning("用量统计初始化失败: %s", str(e)[:100])
    try:
        error_reporter.install()
    except Exception as e:
        logger.warning("错误上报安装失败: %s", str(e)[:100])
    try:
        health_module.start_background_check(load_config)
    except Exception as e:
        logger.warning("健康检查启动失败: %s", str(e)[:100])


@app.on_event("shutdown")
async def shutdown_event():
    """关闭时停止健康检查 + 关闭连接池 + 卸载错误上报"""
    try:
        health_module.stop_background_check()
    except Exception as e:
        logger.warning("健康检查停止失败: %s", str(e)[:100])
    try:
        error_reporter.uninstall()
    except Exception as e:
        logger.warning("错误上报卸载失败: %s", str(e)[:100])
    try:
        await close_client()
    except Exception as e:
        logger.warning("连接池关闭失败: %s", str(e)[:100])


# ============================================================
# 静态文件端点
# ============================================================
@app.get("/")
async def index():
    cfg_html = WEB_DIR / "config.html"
    if not cfg_html.exists():
        return JSONResponse(
            {"error": f"配置页文件不存在: {cfg_html}"},
            status_code=500,
        )
    return FileResponse(cfg_html)


@app.get("/app.js")
async def app_js():
    js_file = WEB_DIR / "app.js"
    if not js_file.exists():
        return JSONResponse({"error": "app.js not found"}, status_code=404)
    return FileResponse(js_file, media_type="application/javascript")


# ============================================================
# 注册路由模块
# ============================================================
from routes.chat import router as chat_router  # noqa: E402
from routes.admin import router as admin_router  # noqa: E402

app.include_router(chat_router)
app.include_router(admin_router)


# ============================================================
# 启动入口
# ============================================================
def run_server(host: str = "127.0.0.1", port: int = 12345):
    """供 tray.py 调用，在子线程跑 uvicorn"""
    import uvicorn
    uvicorn.run(app, host=host, port=port, log_level="warning")
