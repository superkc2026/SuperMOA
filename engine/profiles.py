"""SuperMOA — 多配置 Profile 管理（REQ-20）

Profile 存储为独立 yaml 文件：~/.moa-gateway/profiles/<name>.yaml
默认 profile: "default"（即当前 config.yaml 的副本）
切换 profile 时将 profile 文件复制覆盖 config.yaml。
"""
import logging
import shutil
from pathlib import Path
from typing import List

from engine.config import CONFIG_DIR, CONFIG_FILE, load_config, save_config

logger = logging.getLogger("supermoa")

# Profile 目录
PROFILES_DIR = CONFIG_DIR / "profiles"

# 激活 profile 记录文件（存储当前激活的 profile 名）
ACTIVE_PROFILE_FILE = CONFIG_DIR / ".active_profile"

# 默认 profile 名
DEFAULT_PROFILE_NAME = "default"


def _ensure_profiles_dir() -> None:
    """确保 profiles 目录存在。"""
    PROFILES_DIR.mkdir(parents=True, exist_ok=True)


def _ensure_default_profile() -> None:
    """确保 default profile 存在（从当前 config.yaml 生成）。"""
    _ensure_profiles_dir()
    default_profile = PROFILES_DIR / f"{DEFAULT_PROFILE_NAME}.yaml"
    if not default_profile.exists():
        if CONFIG_FILE.exists():
            shutil.copy2(CONFIG_FILE, default_profile)
            logger.info("从 config.yaml 生成 default profile")
        else:
            # config.yaml 不存在时，用空配置创建
            save_config({})
            shutil.copy2(CONFIG_FILE, default_profile)


def _read_active_profile() -> str:
    """读取当前激活的 profile 名。

    Returns:
        激活的 profile 名，默认为 "default"
    """
    if ACTIVE_PROFILE_FILE.exists():
        try:
            return ACTIVE_PROFILE_FILE.read_text(encoding="utf-8").strip()
        except (IOError, OSError) as e:
            logger.warning("读取 active profile 失败: %s", str(e)[:100])
    return DEFAULT_PROFILE_NAME


def _write_active_profile(name: str) -> None:
    """写入当前激活的 profile 名。

    Args:
        name: profile 名
    """
    try:
        ACTIVE_PROFILE_FILE.write_text(name, encoding="utf-8")
    except (IOError, OSError) as e:
        logger.warning("写入 active profile 失败: %s", str(e)[:100])


def list_profiles() -> List[dict]:
    """列出所有 Profile。

    Returns:
        Profile 列表，每项含 name 和 active 字段。
        例如: [{"name": "default", "active": True}, {"name": "work", "active": False}]
    """
    _ensure_profiles_dir()
    _ensure_default_profile()

    active = _read_active_profile()
    profiles: List[dict] = []

    for f in sorted(PROFILES_DIR.glob("*.yaml")):
        name = f.stem
        profiles.append({
            "name": name,
            "active": name == active,
        })

    return profiles


def get_active_profile() -> str:
    """返回当前激活的 Profile 名。

    Returns:
        激活的 profile 名
    """
    return _read_active_profile()


def switch_profile(name: str) -> bool:
    """切换到指定 Profile。

    将 profile 文件复制覆盖 config.yaml，并记录激活状态。

    Args:
        name: 要切换到的 profile 名

    Returns:
        True 如果切换成功，False 如果 profile 不存在
    """
    _ensure_profiles_dir()
    _ensure_default_profile()

    profile_file = PROFILES_DIR / f"{name}.yaml"
    if not profile_file.exists():
        logger.warning("Profile '%s' 不存在", name)
        return False

    try:
        shutil.copy2(profile_file, CONFIG_FILE)
        _write_active_profile(name)
        logger.info("已切换到 Profile '%s'", name)
        return True
    except (IOError, OSError) as e:
        logger.error("切换 Profile '%s' 失败: %s", name, str(e)[:100])
        return False


def save_current_as_profile(name: str) -> bool:
    """将当前 config.yaml 保存为新 Profile。

    Args:
        name: 新 profile 名

    Returns:
        True 如果保存成功
    """
    _ensure_profiles_dir()

    profile_file = PROFILES_DIR / f"{name}.yaml"
    try:
        if not CONFIG_FILE.exists():
            # config.yaml 不存在时先创建空配置
            save_config({})
        shutil.copy2(CONFIG_FILE, profile_file)
        logger.info("已将当前配置保存为 Profile '%s'", name)
        return True
    except (IOError, OSError) as e:
        logger.error("保存 Profile '%s' 失败: %s", name, str(e)[:100])
        return False


def delete_profile(name: str) -> bool:
    """删除指定 Profile。

    不能删除当前激活的 profile。

    Args:
        name: 要删除的 profile 名

    Returns:
        True 如果删除成功，False 如果 profile 不存在或是当前激活的
    """
    _ensure_profiles_dir()

    active = _read_active_profile()
    if name == active:
        logger.warning("不能删除当前激活的 Profile '%s'", name)
        return False

    profile_file = PROFILES_DIR / f"{name}.yaml"
    if not profile_file.exists():
        logger.warning("Profile '%s' 不存在", name)
        return False

    try:
        profile_file.unlink()
        logger.info("已删除 Profile '%s'", name)
        return True
    except (IOError, OSError) as e:
        logger.error("删除 Profile '%s' 失败: %s", name, str(e)[:100])
        return False
