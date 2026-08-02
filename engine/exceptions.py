"""SuperMOA — 异常类定义

统一异常体系，禁止裸 except: pass，所有 except 均应捕获具体异常并记日志。
"""
import logging
import time
from typing import Optional

logger = logging.getLogger("supermoa")

# 安全审计日志（独立于调用日志，记录敏感操作）
_audit_log: list = []
_MAX_AUDIT = 200


class SuperMOAError(Exception):
    """SuperMOA 基础异常类"""
    pass


class UpstreamError(SuperMOAError):
    """上游模型调用失败（网络错误、HTTP 非 200、响应解析失败等）"""
    pass


class ConfigError(SuperMOAError):
    """配置错误（校验失败、缺失必填字段等）"""
    pass


class NoHealthyReferenceError(SuperMOAError):
    """所有参考模型均不健康"""
    pass


class AllReferencesFailedError(SuperMOAError):
    """所有参考模型均调用失败（重试后仍失败）"""
    pass


class AggregatorNotConfiguredError(SuperMOAError):
    """未配置聚合模型"""
    pass


class AggregatorCallError(SuperMOAError):
    """聚合模型调用失败"""
    pass


class StreamError(SuperMOAError):
    """流式响应错误"""
    pass


def log_and_raise(exc_class: type, message: str) -> None:
    """记录日志并抛出异常的便捷方法。

    Args:
        exc_class: 异常类（必须是 SuperMOAError 的子类）
        message: 异常消息
    """
    logger.error("%s: %s", exc_class.__name__, message)
    raise exc_class(message)


def friendly_error_message(raw_message: str, status_code: int = 0) -> str:
    """将技术性错误消息转换为用户友好的提示。

    识别常见错误模式（HTTP 状态码、异常类型名等），返回通俗易懂的中文提示。
    如果无法识别，返回原始消息（截断后）。

    Args:
        raw_message: 原始错误消息字符串
        status_code: HTTP 状态码（0 表示无状态码）

    Returns:
        友好的错误提示字符串
    """
    if not raw_message:
        return "未知错误"

    msg_lower = raw_message.lower()

    # HTTP 401 / 403 → API Key 问题
    if status_code in (401, 403) or "401" in raw_message or "403" in raw_message:
        return "API Key 不正确，请检查"

    # HTTP 429 → 限流
    if status_code == 429 or "429" in raw_message:
        return "请求过于频繁，请稍后重试"

    # HTTP 404 → 模型不存在
    if status_code == 404 or "404" in raw_message:
        return "模型不存在或地址错误，请检查 Base URL 和模型名"

    # HTTP 500 系列 → 服务端错误
    if status_code >= 500 or "500" in raw_message or "502" in raw_message or "503" in raw_message:
        return "模型服务暂时不可用，请稍后重试"

    # 连接错误类
    if "connecterror" in msg_lower or "connecttimeout" in msg_lower or "connectionerror" in msg_lower:
        return "无法连接模型服务，请检查网络"
    if "timeoutexception" in msg_lower or "timeout" in msg_lower:
        return "请求超时，请检查网络或稍后重试"
    if "httpstatuserro" in msg_lower:
        return "模型调用失败，请检查网络或 API Key"
    if "readtimeout" in msg_lower or "writetimeout" in msg_lower:
        return "请求超时，请检查网络或稍后重试"
    if "proxyerror" in msg_lower or "proxy" in msg_lower:
        return "代理连接失败，请检查代理设置"

    # 通用降级：截断后返回
    return raw_message[:200] if len(raw_message) > 200 else raw_message


# ============================================================
# 统一错误响应格式
# ============================================================

def error_response(code: int, message: str, error_type: str = "error") -> dict:
    """统一错误响应格式：{error: {code, message, type}}

    Args:
        code: HTTP 状态码或自定义错误码
        message: 用户友好的错误消息
        error_type: 错误类型（auth_error/rate_limit/upstream_error/invalid_request/config_error/not_found）
    Returns:
        dict: {"error": {"code": code, "message": message, "type": error_type}}
    """
    return {"error": {"code": code, "message": message, "type": error_type}}


# ============================================================
# 安全审计日志
# ============================================================

def audit_log(action: str, detail: str = "", client: str = "") -> None:
    """记录安全审计日志（敏感操作）

    Args:
        action: 操作类型（regenerate_key/export_config/import_config/toggle_error_reporting/delete_profile/switch_profile）
        detail: 操作详情
        client: 客户端标识
    """
    entry = {
        "ts": time.time(),
        "action": action,
        "detail": detail[:200],
        "client": client[:50],
    }
    _audit_log.append(entry)
    if len(_audit_log) > _MAX_AUDIT:
        _audit_log.pop(0)
    logger.info("[AUDIT] %s: %s (client=%s)", action, detail[:100], client[:30])


def get_audit_logs(limit: int = 50) -> list:
    """获取安全审计日志"""
    return _audit_log[-limit:]
