"""SuperMOA — 版本更新检查模块

启动时或手动触发时检查腾讯云 COS 上的 versions.json，对比当前版本，
有新版时返回更新信息（版本号、下载地址、更新说明）。
不自动下载，仅提示用户。

versions.json 格式：
    {
        "latest": "1.0.0",
        "release_date": "2026-07-30",
        "releases": {
            "1.0.0": {
                "download_url": "https://.../SuperMOA.exe",
                "sha256": "abc123...",
                "release_notes": "首个开源版本",
                "min_required_version": null
            }
        }
    }

API 端点（由 routes/admin.py 集成）：
    GET /api/check-update
    响应: {has_update, current_version, latest_version, download_url, release_notes}
"""
import logging
from datetime import datetime
from typing import Optional

from engine.constants import VERSION, VERSIONS_URL, UPDATE_CHECK_TIMEOUT

logger = logging.getLogger(__name__)

# 请求头（标识客户端身份，便于 CDN 日志统计）
REQUEST_HEADERS = {
    "User-Agent": f"SuperMOA/{VERSION}",
}


def _parse_version(version_str: str) -> tuple:
    """解析版本号字符串为可比较的元组。

    支持格式: "1.0.0", "v1.2.3", "1.0.0-beta" 等。
    忽略预发布标签，仅比较主版本号。

    Args:
        version_str: 版本号字符串，可能含 'v' 前缀或预发布标签

    Returns:
        (major, minor, patch) 三元组，解析失败时返回 (0, 0, 0)
    """
    # 去除前导 v/V
    cleaned = version_str.strip().lstrip("vV")
    # 去除预发布标签（如 -beta, -rc.1）
    base = cleaned.split("-")[0].split("+")[0]
    parts = base.split(".")
    result = []
    for part in parts[:3]:
        try:
            result.append(int(part))
        except ValueError:
            result.append(0)
    # 补齐到三元组
    while len(result) < 3:
        result.append(0)
    return tuple(result[:3])


def _compare_versions(current: str, latest: str) -> int:
    """比较两个版本号。

    Args:
        current: 当前版本号
        latest: 最新版本号

    Returns:
        -1 if current < latest
         0 if current == latest
         1 if current > latest
    """
    cur = _parse_version(current)
    lat = _parse_version(latest)
    if cur < lat:
        return -1
    if cur > lat:
        return 1
    return 0


def _fetch_versions_json() -> Optional[dict]:
    """从腾讯云 COS 获取 versions.json。

    Returns:
        versions.json 解析后的字典，或 None（网络错误/解析失败时）
    """
    try:
        import requests
    except ImportError:
        logger.warning("requests 库未安装，版本检查功能不可用")
        return None

    try:
        resp = requests.get(
            VERSIONS_URL,
            headers=REQUEST_HEADERS,
            timeout=UPDATE_CHECK_TIMEOUT,
        )
    except Exception as exc:
        logger.warning("版本检查网络请求失败: %s", exc)
        return None

    if resp.status_code == 404:
        logger.info("versions.json 不存在（可能是首次发布前）")
        return None
    if resp.status_code != 200:
        logger.warning("versions.json 请求返回非 200: %d", resp.status_code)
        return None

    try:
        data = resp.json()
    except ValueError:
        logger.warning("versions.json 响应解析失败（非 JSON）")
        return None

    return data


def _extract_release_info(versions_data: dict) -> Optional[dict]:
    """从 versions.json 中提取最新版本的发布信息。

    Args:
        versions_data: versions.json 解析后的字典

    Returns:
        发布信息字典:
        {
            "version": str,
            "download_url": str,
            "release_notes": str,
        }
        或 None（数据格式异常时）
    """
    latest_version = versions_data.get("latest", "")
    if not latest_version:
        logger.warning("versions.json 中缺少 latest 字段")
        return None

    releases = versions_data.get("releases", {})
    if not isinstance(releases, dict):
        logger.warning("versions.json 中 releases 字段格式异常")
        return None

    release_info = releases.get(latest_version)
    if not release_info or not isinstance(release_info, dict):
        logger.warning("versions.json 中未找到版本 %s 的发布信息", latest_version)
        return None

    return {
        "version": latest_version,
        "download_url": release_info.get("download_url", ""),
        "release_notes": release_info.get("release_notes", ""),
    }


def check_for_update() -> dict:
    """检查是否有新版本可用。

    对比当前版本（constants.VERSION）与腾讯云 versions.json 中的最新版本。
    不自动下载，仅返回更新信息。
    网络错误时 graceful fallback（返回 has_update=False）。

    Returns:
        更新信息字典:
        {
            "has_update": bool,
            "current_version": str,
            "latest_version": str,
            "download_url": str,
            "release_notes": str,
        }
    """
    # 无新版时的默认返回（网络错误等 fallback 场景）
    no_update_result = {
        "has_update": False,
        "current_version": VERSION,
        "latest_version": VERSION,
        "download_url": "",
        "release_notes": "",
    }

    versions_data = _fetch_versions_json()
    if versions_data is None:
        return no_update_result

    release_info = _extract_release_info(versions_data)
    if release_info is None:
        return no_update_result

    latest_version = release_info["version"]
    download_url = release_info["download_url"]
    release_notes = release_info["release_notes"]

    has_update = _compare_versions(VERSION, latest_version) < 0

    if has_update:
        logger.info(
            "发现新版本: 当前 %s → 最新 %s", VERSION, latest_version
        )
    else:
        logger.info("当前版本 %s 已是最新", VERSION)

    return {
        "has_update": has_update,
        "current_version": VERSION,
        "latest_version": latest_version,
        "download_url": download_url,
        "release_notes": release_notes,
    }


class UpdateChecker:
    """版本更新检查器，支持手动触发和缓存上次检查时间。"""

    def __init__(self) -> None:
        self._last_check_time: Optional[datetime] = None
        self._last_result: Optional[dict] = None

    def check(self, force: bool = False) -> dict:
        """执行版本检查。

        Args:
            force: 是否强制重新检查（忽略缓存）

        Returns:
            更新信息字典（同 check_for_update 返回值）
        """
        if not force and self._last_result is not None:
            return self._last_result

        result = check_for_update()
        self._last_check_time = datetime.now()
        self._last_result = result
        return result

    @property
    def last_check_time(self) -> Optional[datetime]:
        """上次检查时间"""
        return self._last_check_time

    @property
    def last_result(self) -> Optional[dict]:
        """上次检查结果"""
        return self._last_result
