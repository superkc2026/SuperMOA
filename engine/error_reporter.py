"""SuperMOA — 错误上报模块（opt-in 本地日志）

默认关闭。用户可在配置页开启（opt-in）。
开启后：未捕获的异常写入 ~/.moa-gateway/errors.jsonl（脱敏堆栈，不含请求内容）。
不联网上报（仅本地文件）。
配置项存 config.yaml 的 error_reporting.enabled（默认 false）。
"""
import json
import logging
import re
import sys
import traceback
from datetime import datetime
from pathlib import Path
from typing import Optional

from engine.config import CONFIG_DIR, load_config
from engine.constants import VERSION

logger = logging.getLogger(__name__)

# ============================================================
# 文件路径
# ============================================================
ERROR_LOG_FILE = CONFIG_DIR / "errors.jsonl"
MAX_ERROR_FILE_SIZE = 5 * 1024 * 1024  # 5MB，超过后自动轮转
MAX_ERROR_ENTRIES = 1000  # 最多保留条目数

# ============================================================
# 脱敏正则模式
# ============================================================
# API Key 模式（sk-moa-xxx, sk-xxx, sk-ant-xxx 等）
_SENSITIVE_PATTERNS: list[tuple[re.Pattern, str]] = [
    # API Key: sk-moa-xxxxx
    (re.compile(r"sk-moa-[a-zA-Z0-9]+"), "***REDACTED_KEY***"),
    # API Key: sk-ant-xxxxx
    (re.compile(r"sk-ant-[a-zA-Z0-9-]+"), "***REDACTED_KEY***"),
    # API Key: sk-xxxxx (通用 OpenAI 格式)
    (re.compile(r"sk-[a-zA-Z0-9]{20,}"), "***REDACTED_KEY***"),
    # Bearer token
    (re.compile(r"(Bearer\s+)[a-zA-Z0-9\-._~+/]+", re.IGNORECASE), r"\1***REDACTED_TOKEN***"),
    # URL 中的用户名:密码: https://user:pass@host
    (re.compile(r"(https?://[^:/\s]+:)([^\s@/]+)(@)", re.IGNORECASE), r"\1***REDACTED***\3"),
    # api_key 字段值: "api_key": "value" 或 api_key=value
    (re.compile(r'''(['"]?api[_-]?key['"]?\s*[:=]\s*['"])([^'"]+)(['"])''', re.IGNORECASE), r"\1***REDACTED***\3"),
    # authorization 头
    (re.compile(r'''(['"]?authorization['"]?\s*[:=]\s*['"])([^'"]+)(['"])''', re.IGNORECASE), r"\1***REDACTED***\3"),
    # password 字段
    (re.compile(r'''(['"]?password['"]?\s*[:=]\s*['"])([^'"]+)(['"])''', re.IGNORECASE), r"\1***REDACTED***\3"),
    # token 字段
    (re.compile(r'''(['"]?token['"]?\s*[:=]\s*['"])([^'"]+)(['"])''', re.IGNORECASE), r"\1***REDACTED***\3"),
]


def _sanitize_text(text: str) -> str:
    """对文本进行脱敏处理，移除敏感信息。

    使用正则替换移除 API Key、Bearer Token、URL 凭据、密码字段等。

    Args:
        text: 原始文本

    Returns:
        脱敏后的文本
    """
    if not text:
        return text
    result = text
    for pattern, replacement in _SENSITIVE_PATTERNS:
        result = pattern.sub(replacement, result)
    return result


def _sanitize_traceback(tb_text: str) -> str:
    """对 traceback 文本进行脱敏。

    在 _sanitize_text 基础上，额外移除局部变量值中的长字符串
    （防止请求体内容泄漏到堆栈中）。

    Args:
        tb_text: 原始 traceback 字符串

    Returns:
        脱敏后的 traceback 字符串
    """
    # 先做通用脱敏
    result = _sanitize_text(tb_text)
    # 移除 traceback 中局部变量区域的长字符串值
    # 匹配 "var = '很长的字符串...'" 或 "var = "很长的字符串...""
    # 仅保留变量名，截断超过 100 字符的字符串值
    result = re.sub(
        r"(\s+\w+\s*=\s*)(['\"])((?:.|\n){100,})\2",
        r"\1\2***TRUNCATED***\2",
        result,
    )
    return result


def _build_error_entry(exc_type: type, exc_value: BaseException, exc_tb) -> dict:
    """构造一条脱敏的错误日志条目。

    Args:
        exc_type: 异常类型
        exc_value: 异常实例
        exc_tb: traceback 对象

    Returns:
        JSON 可序列化的字典:
        {
            "timestamp": ISO 时间,
            "type": 异常类型名,
            "message": 脱敏后的错误消息,
            "traceback": 脱敏后的堆栈文本,
            "version": 当前版本号,
        }
    """
    # 生成完整 traceback 文本
    tb_lines = traceback.format_exception(exc_type, exc_value, exc_tb)
    raw_tb = "".join(tb_lines)

    # 脱敏处理
    sanitized_tb = _sanitize_traceback(raw_tb)
    sanitized_msg = _sanitize_text(str(exc_value))

    return {
        "timestamp": datetime.now().isoformat(),
        "type": exc_type.__name__ if exc_type else "Unknown",
        "message": sanitized_msg[:500],  # 截断超长消息
        "traceback": sanitized_tb,
        "version": VERSION,
    }


def _rotate_error_file() -> None:
    """如果错误日志文件超过阈值，执行轮转清理。

    保留最新 MAX_ERROR_ENTRIES 条记录。
    """
    if not ERROR_LOG_FILE.exists():
        return

    try:
        file_size = ERROR_LOG_FILE.stat().st_size
    except OSError:
        return

    if file_size <= MAX_ERROR_FILE_SIZE:
        return

    # 读取所有行
    try:
        lines = ERROR_LOG_FILE.read_text(encoding="utf-8").strip().split("\n")
    except (OSError, UnicodeDecodeError):
        return

    # 保留最新的条目
    valid_lines = [line for line in lines if line.strip()]
    if len(valid_lines) <= MAX_ERROR_ENTRIES:
        return

    kept_lines = valid_lines[-MAX_ERROR_ENTRIES:]
    try:
        ERROR_LOG_FILE.write_text(
            "\n".join(kept_lines) + "\n", encoding="utf-8"
        )
        logger.info("错误日志已轮转，保留 %d 条记录", len(kept_lines))
    except OSError as exc:
        logger.warning("错误日志轮转失败: %s", exc)


def _write_error_entry(entry: dict) -> None:
    """将一条错误条目追加写入 errors.jsonl 文件。

    Args:
        entry: 错误条目字典
    """
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    # 先检查是否需要轮转
    _rotate_error_file()

    line = json.dumps(entry, ensure_ascii=False)
    try:
        with open(ERROR_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError as exc:
        logger.warning("写入错误日志失败: %s", exc)


def is_error_reporting_enabled() -> bool:
    """检查错误上报是否已开启。

    从 config.yaml 读取 error_reporting.enabled 配置项。
    默认为 False（opt-in）。

    Returns:
        True 如果已开启，False 如果关闭或配置缺失
    """
    try:
        config = load_config()
    except Exception:
        return False

    error_config = config.get("error_reporting") or {}
    return bool(error_config.get("enabled", False))


def report_exception(
    exc_type: type,
    exc_value: BaseException,
    exc_tb,
) -> None:
    """报告一个未捕获的异常（脱敏后写入本地文件）。

    如果错误上报未开启，则不做任何操作。

    Args:
        exc_type: 异常类型
        exc_value: 异常实例
        exc_tb: traceback 对象
    """
    if not is_error_reporting_enabled():
        return

    entry = _build_error_entry(exc_type, exc_value, exc_tb)
    _write_error_entry(entry)
    logger.debug("已记录错误条目: %s", entry.get("type", "Unknown"))


def _default_excepthook(
    exc_type: type,
    exc_value: BaseException,
    exc_tb,
) -> None:
    """全局未捕获异常钩子。

    替换 sys.excepthook，在输出到 stderr 的同时记录脱敏错误日志。

    Args:
        exc_type: 异常类型
        exc_value: 异常实例
        exc_tb: traceback 对象
    """
    # 先调用默认行为（输出到 stderr）
    if sys.__excepthook__ is not None:
        sys.__excepthook__(exc_type, exc_value, exc_tb)

    # 记录到本地文件
    try:
        report_exception(exc_type, exc_value, exc_tb)
    except Exception as exc:
        # 错误上报本身出错时不能影响主程序
        logger.warning("错误上报写入失败: %s", exc)


_original_excepthook: Optional[callable] = None
_is_installed: bool = False


def install() -> bool:
    """安装全局异常钩子，启用错误上报。

    仅当错误上报在配置中已开启时才实际安装。
    可安全重复调用。

    Returns:
        True 如果已安装，False 如果未开启或安装失败
    """
    global _original_excepthook, _is_installed

    if _is_installed:
        return True

    if not is_error_reporting_enabled():
        logger.debug("错误上报未开启，跳过安装")
        return False

    _original_excepthook = sys.excepthook
    sys.excepthook = _default_excepthook
    _is_installed = True
    logger.info("错误上报已安装（opt-in），未捕获异常将记录到 %s", ERROR_LOG_FILE)
    return True


def uninstall() -> None:
    """卸载全局异常钩子，恢复默认行为。

    可安全重复调用。
    """
    global _original_excepthook, _is_installed

    if not _is_installed:
        return

    if _original_excepthook is not None:
        sys.excepthook = _original_excepthook
    _original_excepthook = None
    _is_installed = False
    logger.info("错误上报已卸载")


def get_error_log_path() -> Path:
    """返回错误日志文件路径。"""
    return ERROR_LOG_FILE


def clear_error_log() -> bool:
    """清空错误日志文件。

    Returns:
        True 如果清除成功，False 如果失败
    """
    try:
        if ERROR_LOG_FILE.exists():
            ERROR_LOG_FILE.unlink()
        return True
    except OSError as exc:
        logger.warning("清除错误日志失败: %s", exc)
        return False


def get_error_entries(limit: int = 100) -> list[dict]:
    """读取最近的错误日志条目。

    Args:
        limit: 最多返回的条目数（从最新开始）

    Returns:
        错误条目字典列表，最新的在前
    """
    if not ERROR_LOG_FILE.exists():
        return []

    try:
        lines = ERROR_LOG_FILE.read_text(encoding="utf-8").strip().split("\n")
    except (OSError, UnicodeDecodeError):
        return []

    entries: list[dict] = []
    for line in reversed(lines):
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
            entries.append(entry)
        except json.JSONDecodeError:
            continue
        if len(entries) >= limit:
            break

    return entries
