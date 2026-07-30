"""SuperMOA — 后台健康检查

启动时 + 每 5 分钟对配置的所有模型发 ping，结果存内存。
orchestrator 调度时跳过不健康参考模型；main.py 暴露 /api/health-status。
"""
import asyncio
import logging
import threading
import time
from typing import Dict, Optional, Callable

import httpx

from engine import constants as C
from engine.http_client import get_client

logger = logging.getLogger("supermoa")

# ============================================================
# 内存状态
# ============================================================
_health_status: Dict[str, dict] = {}
_lock = threading.Lock()
_check_thread: Optional[threading.Thread] = None
_stop_event = threading.Event()

CHECK_INTERVAL = C.HEALTH_CHECK_INTERVAL  # 5 分钟


# ============================================================
# 单模型 ping
# ============================================================
async def _ping_model(model_cfg: dict) -> tuple:
    """ping 单个模型，返回 (healthy: bool, error: str)

    健康检查在独立线程的事件循环中运行，无法复用主线程的全局 client，
    因此每次创建临时 client（短超时，ping 请求轻量）。
    """
    try:
        async with httpx.AsyncClient(timeout=C.HEALTH_CHECK_TIMEOUT) as client:
            resp = await client.post(
                f"{model_cfg.get('base_url', '').rstrip('/')}/chat/completions",
                json={
                    "model": model_cfg.get("model", ""),
                    "messages": [{"role": "user", "content": "ping"}],
                    "max_tokens": 1,
                    "temperature": 0,
                },
                headers={
                    "Authorization": f"Bearer {model_cfg.get('api_key', '')}",
                    "Content-Type": "application/json",
                },
            )
        if resp.status_code == 200:
            return True, ""
        return False, f"HTTP {resp.status_code}: {resp.text[:100]}"
    except Exception as e:
        logger.warning("健康检查单模型 ping 失败: %s", str(e)[:100])
        return False, f"{type(e).__name__}: {str(e)[:100]}"


# ============================================================
# 批量检查
# ============================================================
async def _check_all_models(config: dict):
    """检查所有配置的模型（参考 + 聚合 + 透传）"""
    models_to_check = []

    for ref in config.get("reference_models") or []:
        models_to_check.append((ref.get("name", "ref"), ref))

    agg = config.get("aggregator")
    if agg:
        models_to_check.append((agg.get("name", "aggregator"), agg))

    pass_cfg = config.get("default_passthrough")
    if pass_cfg:
        models_to_check.append((pass_cfg.get("name", "passthrough"), pass_cfg))

    if not models_to_check:
        return

    tasks = [_ping_model(cfg) for _, cfg in models_to_check]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    with _lock:
        for (name, _), result in zip(models_to_check, results):
            if isinstance(result, Exception):
                _health_status[name] = {
                    "healthy": False,
                    "last_check": time.time(),
                    "error": f"{type(result).__name__}: {str(result)[:100]}",
                }
            else:
                healthy, error = result
                _health_status[name] = {
                    "healthy": healthy,
                    "last_check": time.time(),
                    "error": error,
                }


def run_health_check_once(config: dict):
    """同步入口：在独立事件循环里跑一次健康检查"""
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(_check_all_models(config))
        finally:
            loop.close()
    except Exception as e:
        logger.warning("健康检查执行失败: %s", str(e)[:100])


# ============================================================
# 后台线程
# ============================================================
def start_background_check(config_loader: Callable[[], dict]):
    """启动后台健康检查线程

    config_loader: 无参 callable，返回当前 config dict（每次检查时重新加载）
    """
    global _check_thread, _stop_event
    if _check_thread and _check_thread.is_alive():
        return

    _stop_event = threading.Event()

    def _loop():
        # 启动时立即检查一次
        try:
            config = config_loader()
            run_health_check_once(config)
        except Exception as e:
            logger.warning("健康检查初始化失败: %s", str(e)[:100])

        while not _stop_event.wait(CHECK_INTERVAL):
            try:
                config = config_loader()
                run_health_check_once(config)
            except Exception as e:
                logger.warning("健康检查周期执行失败: %s", str(e)[:100])

    _check_thread = threading.Thread(target=_loop, daemon=True, name="moa-health-check")
    _check_thread.start()


def stop_background_check():
    """停止后台健康检查"""
    global _stop_event
    _stop_event.set()


# ============================================================
# 查询接口
# ============================================================
def is_model_healthy(name: str) -> bool:
    """查询某个模型是否健康。未知模型返回 True（不阻塞，避免误杀）"""
    with _lock:
        status = _health_status.get(name)
        if status is None:
            return True
        return status["healthy"]


def get_health_status() -> dict:
    """返回所有模型的健康状态快照"""
    with _lock:
        return {name: dict(s) for name, s in _health_status.items()}


def clear_health_status():
    """清空健康状态（配置变更后用）"""
    with _lock:
        _health_status.clear()
