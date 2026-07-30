"""SuperMOA — httpx 全局连接池管理

复用 httpx.AsyncClient 连接池，避免每次请求新建 client。
生命周期：启动时创建（startup），关闭时清理（shutdown）。
"""
import logging
from typing import Optional

import httpx

from engine import constants as C

logger = logging.getLogger("supermoa")

# 全局 AsyncClient 单例
_global_client: Optional[httpx.AsyncClient] = None


def get_client(timeout: float = C.DEFAULT_HTTP_TIMEOUT) -> httpx.AsyncClient:
    """获取全局 httpx AsyncClient 实例。

    如果全局实例不存在或已关闭，创建新实例。
    使用连接池复用 TCP 连接，减少握手开销。

    Args:
        timeout: 请求超时时间（秒），仅在新创建时生效

    Returns:
        httpx.AsyncClient 实例
    """
    global _global_client
    if _global_client is None or _global_client.is_closed:
        _global_client = httpx.AsyncClient(
            timeout=timeout,
            limits=httpx.Limits(
                max_connections=100,
                max_keepalive_connections=20,
                keepalive_expiry=30,
            ),
        )
        logger.info("全局 httpx AsyncClient 已创建（连接池复用）")
    return _global_client


async def close_client() -> None:
    """关闭全局 httpx AsyncClient，释放连接池资源。

    在应用 shutdown 时调用。
    """
    global _global_client
    if _global_client is not None and not _global_client.is_closed:
        await _global_client.aclose()
        logger.info("全局 httpx AsyncClient 已关闭")
    _global_client = None
