"""SuperMOA — 日志管理（记录/加载/轮转/去重）

封装请求日志的完整生命周期：
- 记录：带去重逻辑（agent 循环/多轮对话重复请求跳过）
- 加载：启动时从 logs.jsonl 加载历史日志
- 轮转：按大小滚动（超过 LOG_ROTATION_MAX_SIZE 时重命名，保留最近 N 份）
- 查询：返回内存中的日志列表
"""
import json
import logging
import os
import time
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from engine import constants as C

logger = logging.getLogger("supermoa")


class LogManager:
    """请求日志管理器（单例模式，全局共享一个实例）。

    职责：
    1. 内存中维护最近 MAX_REQUEST_LOGS 条日志
    2. 持久化到 logs.jsonl 文件
    3. 日志去重（agent 循环/多轮对话重复请求跳过）
    4. 日志文件轮转（按大小滚动）
    """

    def __init__(self, log_file: Optional[Path] = None):
        """初始化日志管理器。

        Args:
            log_file: 日志文件路径，None 时不持久化
        """
        self._log_file: Optional[Path] = log_file
        self._logs: List[dict] = []

    @property
    def log_file(self) -> Optional[Path]:
        """返回当前日志文件路径。"""
        return self._log_file

    @log_file.setter
    def log_file(self, value: Optional[Path]):
        """设置日志文件路径。"""
        self._log_file = value

    def load_logs(self) -> List[dict]:
        """从日志文件加载历史日志到内存。

        读取最近 MAX_REQUEST_LOGS 条记录，最新的在列表前部。

        Returns:
            加载的日志列表
        """
        if not self._log_file or not self._log_file.exists():
            return []

        try:
            content = self._log_file.read_text(encoding="utf-8")
            lines = content.strip().split("\n")
            # 从最后往前读取，取最近 MAX_REQUEST_LOGS 条
            loaded: List[dict] = []
            for line in reversed(lines[-C.MAX_REQUEST_LOGS:]):
                line = line.strip()
                if not line:
                    continue
                try:
                    loaded.append(json.loads(line))
                except (json.JSONDecodeError, ValueError) as e:
                    logger.warning("历史日志解析失败: %s", str(e)[:100])
            # 反转使最新的在前
            loaded.reverse()
            self._logs = loaded
            logger.info("加载了 %d 条历史日志", len(loaded))
        except (IOError, OSError) as e:
            logger.warning("日志文件读取失败: %s", str(e)[:100])
            self._logs = []

        return self._logs

    def get_logs(self) -> List[dict]:
        """返回内存中的日志列表（最新的在前）。"""
        return self._logs

    def log_request(
        self,
        model_field: str,
        route: str,
        actual_model: str,
        prefix: str,
        prompt_preview: str,
        client: str = "",
        is_user_message: bool = False,
    ) -> bool:
        """记录一条请求日志，带去重逻辑。

        去重规则：
        1. 非用户首次消息：完全相同的 prompt_preview + LOG_DEDUP_WINDOW_SECONDS 秒内 → 跳过
        2. 所有请求：当前 preview 比之前的长且包含之前的（多轮对话带历史）→ 跳过

        Args:
            model_field: 请求中的 model 字段
            route: 路由类型 ("moa" 或 "passthrough")
            actual_model: 实际调用的模型名
            prefix: 触发词
            prompt_preview: 消息预览文本
            client: 客户端来源标识
            is_user_message: 是否是用户首次消息

        Returns:
            True 表示已记录，False 表示被去重跳过
        """
        now_ts = time.time()
        now_str = datetime.now().strftime("%H:%M:%S")

        _preview = prompt_preview[:C.LOG_PREVIEW_LENGTH]
        _full_preview = prompt_preview[:C.LOG_PREVIEW_FULL_LENGTH]

        # 去重检查
        for existing in self._logs[:5]:
            existing_pv = existing.get("prompt_preview", "")
            if not is_user_message:
                # agent 循环/多轮对话：完全相同 + 时间窗口内 → 跳过
                if existing_pv == _preview:
                    existing_ts = existing.get("ts", 0)
                    if now_ts - existing_ts < C.LOG_DEDUP_WINDOW_SECONDS:
                        return False
            # 所有请求都检查：当前 preview 比之前的长且包含之前的 → 跳过
            if (
                existing_pv
                and len(existing_pv) > 5
                and len(_full_preview) > len(existing_pv) + 5
                and existing_pv in _full_preview
            ):
                return False

        entry = {
            "ts": now_ts,
            "time": now_str,
            "model_field": model_field,
            "route": route,
            "actual_model": actual_model,
            "prefix": prefix,
            "prompt_preview": _preview,
            "client": client,
        }

        # 插入到列表头部
        self._logs.insert(0, entry)
        if len(self._logs) > C.MAX_REQUEST_LOGS:
            self._logs.pop()

        # 持久化到文件
        self._append_to_file(entry)

        return True

    def _append_to_file(self, entry: dict) -> None:
        """将日志条目追加到文件，并在需要时触发轮转。

        Args:
            entry: 日志条目 dict
        """
        if not self._log_file:
            return

        try:
            # 检查是否需要轮转（写入前检查）
            self._rotate_if_needed()

            with open(self._log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except (IOError, OSError) as e:
            logger.warning("日志持久化失败: %s", str(e)[:100])

    def _rotate_if_needed(self) -> None:
        """检查日志文件大小，超过阈值时执行轮转。

        轮转策略：
        - logs.jsonl → logs.jsonl.1
        - logs.jsonl.1 → logs.jsonl.2
        - ...保留最近 LOG_ROTATION_KEEP_FILES 份
        - 超出的旧文件删除
        - 轮转后新建空 logs.jsonl
        """
        if not self._log_file or not self._log_file.exists():
            return

        try:
            file_size = self._log_file.stat().st_size
        except OSError:
            return

        if file_size < C.LOG_ROTATION_MAX_SIZE:
            return

        logger.info("日志文件超过 %dMB，执行轮转", C.LOG_ROTATION_MAX_SIZE // (1024 * 1024))

        try:
            # 删除超出保留数量的最旧文件
            oldest = self._log_file.parent / f"{self._log_file.name}.{C.LOG_ROTATION_KEEP_FILES}"
            if oldest.exists():
                oldest.unlink()

            # 从旧到新依次重命名：.2→.3(删), .1→.2, 当前→.1
            for i in range(C.LOG_ROTATION_KEEP_FILES - 1, 0, -1):
                src = self._log_file.parent / f"{self._log_file.name}.{i}"
                dst = self._log_file.parent / f"{self._log_file.name}.{i + 1}"
                if src.exists():
                    src.rename(dst)

            # 当前文件重命名为 .1
            rotated = self._log_file.parent / f"{self._log_file.name}.1"
            self._log_file.rename(rotated)

            # 新建空文件
            self._log_file.touch()

            logger.info("日志轮转完成: %s → %s", self._log_file.name, rotated.name)
        except (OSError, IOError) as e:
            logger.warning("日志轮转失败: %s", str(e)[:100])


# 全局单例
_log_manager: Optional[LogManager] = None


def get_log_manager() -> LogManager:
    """获取全局日志管理器单例。

    Returns:
        LogManager 实例
    """
    global _log_manager
    if _log_manager is None:
        _log_manager = LogManager()
    return _log_manager


def init_log_manager(log_file: Path) -> LogManager:
    """初始化全局日志管理器，设置日志文件路径并加载历史日志。

    Args:
        log_file: 日志文件路径

    Returns:
        初始化后的 LogManager 实例
    """
    mgr = get_log_manager()
    mgr.log_file = log_file
    mgr.load_logs()
    return mgr
