"""SuperMOA — 用量统计（SQLite 存储）

记录每次模型调用的 token 用量和成本，按天聚合查询。
存储位置：~/.moa-gateway/usage.db
"""
import logging
import sqlite3
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from engine import constants as C

logger = logging.getLogger("supermoa")

# 全局 DB 路径 + 锁
_db_path: Optional[Path] = None
_db_lock = threading.Lock()

# 建表 SQL
_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS usage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    model TEXT NOT NULL,
    route TEXT NOT NULL,
    prompt_tokens INTEGER DEFAULT 0,
    completion_tokens INTEGER DEFAULT 0,
    total_tokens INTEGER DEFAULT 0,
    cost REAL DEFAULT 0.0,
    client TEXT DEFAULT '',
    ts TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_usage_date ON usage(date);
CREATE INDEX IF NOT EXISTS idx_usage_model ON usage(model);
"""


def init_usage_db(db_dir: Path) -> None:
    """初始化用量统计数据库，创建表和索引。

    Args:
        db_dir: 数据库目录路径（通常为 ~/.moa-gateway/）
    """
    global _db_path
    _db_path = db_dir / "usage.db"
    db_dir.mkdir(parents=True, exist_ok=True)
    try:
        with _db_lock:
            conn = sqlite3.connect(str(_db_path))
            try:
                conn.executescript(_CREATE_TABLE_SQL)
                conn.commit()
            finally:
                conn.close()
        logger.info("用量统计数据库已初始化: %s", _db_path)
    except sqlite3.Error as e:
        logger.warning("用量统计数据库初始化失败: %s", str(e)[:100])


def record_usage(
    model: str,
    route: str,
    prompt_tokens: int,
    completion_tokens: int,
    cost: float = 0.0,
    client: str = "",
) -> None:
    """记录一次模型调用的用量。

    Args:
        model: 模型名称
        route: 路由类型（moa / passthrough）
        prompt_tokens: 输入 token 数
        completion_tokens: 输出 token 数
        cost: 成本（元）
        client: 客户端来源
    """
    if _db_path is None:
        logger.debug("用量统计未初始化，跳过记录")
        return

    now = datetime.now()
    total = prompt_tokens + completion_tokens
    ts_str = now.isoformat()
    date_str = now.strftime("%Y-%m-%d")

    try:
        with _db_lock:
            conn = sqlite3.connect(str(_db_path))
            try:
                conn.execute(
                    """INSERT INTO usage (date, model, route, prompt_tokens, completion_tokens, total_tokens, cost, client, ts)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (date_str, model, route, prompt_tokens, completion_tokens, total, cost, client, ts_str),
                )
                conn.commit()
            finally:
                conn.close()
    except sqlite3.Error as e:
        logger.warning("用量记录失败: %s", str(e)[:100])


def get_usage_summary(days: int = 7) -> list:
    """返回近 N 天的用量汇总（按天+模型聚合）。

    Args:
        days: 查询天数（默认 7）

    Returns:
        汇总列表，每项含 date, model, route, prompt_tokens, completion_tokens, total_tokens, cost, count
    """
    if _db_path is None or not _db_path.exists():
        return []

    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    try:
        with _db_lock:
            conn = sqlite3.connect(str(_db_path))
            try:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute(
                    """SELECT date, model, route,
                              SUM(prompt_tokens) as prompt_tokens,
                              SUM(completion_tokens) as completion_tokens,
                              SUM(total_tokens) as total_tokens,
                              SUM(cost) as cost,
                              COUNT(*) as count
                       FROM usage
                       WHERE date >= ?
                       GROUP BY date, model, route
                       ORDER BY date DESC, model""",
                    (cutoff,),
                )
                rows = cursor.fetchall()
                return [dict(row) for row in rows]
            finally:
                conn.close()
    except sqlite3.Error as e:
        logger.warning("用量查询失败: %s", str(e)[:100])
        return []


def get_usage_total(days: int = 7) -> dict:
    """返回近 N 天的总量汇总。

    Args:
        days: 查询天数

    Returns:
        dict: {total_tokens, total_cost, total_requests, prompt_tokens, completion_tokens}
    """
    if _db_path is None or not _db_path.exists():
        return {
            "total_tokens": 0,
            "total_cost": 0.0,
            "total_requests": 0,
            "prompt_tokens": 0,
            "completion_tokens": 0,
        }

    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    try:
        with _db_lock:
            conn = sqlite3.connect(str(_db_path))
            try:
                cursor = conn.execute(
                    """SELECT
                           SUM(prompt_tokens) as prompt_tokens,
                           SUM(completion_tokens) as completion_tokens,
                           SUM(total_tokens) as total_tokens,
                           SUM(cost) as cost,
                           COUNT(*) as count
                       FROM usage
                       WHERE date >= ?""",
                    (cutoff,),
                )
                row = cursor.fetchone()
                if row and row[0] is not None:
                    return {
                        "prompt_tokens": row[0] or 0,
                        "completion_tokens": row[1] or 0,
                        "total_tokens": row[2] or 0,
                        "total_cost": round(row[3] or 0.0, 4),
                        "total_requests": row[4] or 0,
                    }
                return {
                    "total_tokens": 0,
                    "total_cost": 0.0,
                    "total_requests": 0,
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                }
            finally:
                conn.close()
    except sqlite3.Error as e:
        logger.warning("用量总量查询失败: %s", str(e)[:100])
        return {
            "total_tokens": 0,
            "total_cost": 0.0,
            "total_requests": 0,
            "prompt_tokens": 0,
            "completion_tokens": 0,
        }


def calculate_cost(model: str, base_url: str, prompt_tokens: int, completion_tokens: int) -> float:
    """根据厂商价格计算单次调用成本。

    价格单位：元/百万 token。从 vendors.py 的 model_info 获取。

    Args:
        model: 模型名称
        base_url: 模型 base_url（用于匹配厂商）
        prompt_tokens: 输入 token 数
        completion_tokens: 输出 token 数

    Returns:
        成本（元），找不到价格时返回 0.0
    """
    from engine.vendors import VENDORS

    price_input = 0.0
    price_output = 0.0

    for v in VENDORS:
        if v.get("base_url") == base_url:
            model_info = v.get("model_info", {})
            info = model_info.get(model)
            if info:
                price_input = info.get("price_input", 0.0)
                price_output = info.get("price_output", 0.0)
            break

    if price_input == 0 and price_output == 0:
        return 0.0

    # 价格单位是元/百万 token
    cost = (prompt_tokens / 1_000_000 * price_input) + (completion_tokens / 1_000_000 * price_output)
    return round(cost, 6)
