"""SuperMOA — API Key 管理（bcrypt hash 存储 + 常量时间比较 + 限流）"""
import os
import sys
import logging
import secrets
import time
from pathlib import Path
from collections import defaultdict, deque

import bcrypt

from engine import constants as C

logger = logging.getLogger("supermoa")

CONFIG_DIR = Path.home() / ".moa-gateway"
KEY_FILE = CONFIG_DIR / ".api_key"           # 加密存储的 API Key（DPAPI / Fernet）
KEY_HASH_FILE = CONFIG_DIR / ".api_key_hash" # bcrypt hash（校验用）
KEYFILE_PATH = CONFIG_DIR / ".keyfile"       # Fernet 密钥文件（非 Windows 平台 fallback）

# 限流：每 key 每分钟 N 请求
RATE_LIMIT_WINDOW = C.RATE_LIMIT_WINDOW          # 秒
RATE_LIMIT_MAX_REQUESTS = C.RATE_LIMIT_MAX_REQUESTS    # 每 key 每分钟 60 次

# 内存中的请求记录（进程级）
_request_log: dict = defaultdict(deque)


# ============================================================
# 密钥加密（DPAPI / Fernet）
# ============================================================
def _get_crypto_backend() -> str:
    """检测可用的加密后端：dpapi > fernet > none"""
    if sys.platform == "win32":
        try:
            import win32crypt  # noqa: F401
            return "dpapi"
        except ImportError:
            pass
    try:
        from cryptography.fernet import Fernet  # noqa: F401
        return "fernet"
    except ImportError:
        return "none"


_CRYPTO_BACKEND = _get_crypto_backend()


def _encrypt_key(key: str) -> bytes:
    """加密 API Key 用于安全存储。

    Windows: DPAPI（用户级密钥，无需额外密钥文件）
    macOS/Linux: Fernet（密钥存 ~/.moa-gateway/.keyfile）
    无可用库时: 明文存储（降级，记录警告）
    """
    if _CRYPTO_BACKEND == "dpapi":
        import win32crypt
        return win32crypt.CryptProtectData(
            key.encode("utf-8"), None, None, None, None, 0
        )
    elif _CRYPTO_BACKEND == "fernet":
        from cryptography.fernet import Fernet
        if not KEYFILE_PATH.exists():
            fernet_key = Fernet.generate_key()
            KEYFILE_PATH.write_bytes(fernet_key)
            _set_private_permissions(KEYFILE_PATH)
        else:
            fernet_key = KEYFILE_PATH.read_bytes()
        return Fernet(fernet_key).encrypt(key.encode("utf-8"))
    else:
        logger.warning("无可用加密库（pywin32/cryptography），API Key 将以明文存储")
        return key.encode("utf-8")


def _decrypt_key(encrypted: bytes) -> str:
    """解密 API Key。解密失败时抛出异常（调用方负责处理迁移）。"""
    if _CRYPTO_BACKEND == "dpapi":
        import win32crypt
        return win32crypt.CryptUnprotectData(
            encrypted, None, None, None, 0
        )[1].decode("utf-8")
    elif _CRYPTO_BACKEND == "fernet":
        from cryptography.fernet import Fernet
        fernet_key = KEYFILE_PATH.read_bytes()
        return Fernet(fernet_key).decrypt(encrypted).decode("utf-8")
    else:
        return encrypted.decode("utf-8")


def generate_api_key() -> str:
    """生成 sk-moa- 前缀 + 32 位 hex，共 39 字符"""
    return f"sk-moa-{secrets.token_hex(16)}"


def ensure_api_key() -> str:
    """首次启动自动生成 key，返回明文 key（仅启动时一次性返回）。

    若检测到旧版明文文件，自动加密迁移后覆盖。
    """
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    if KEY_FILE.exists():
        raw = KEY_FILE.read_bytes()
        # 尝试解密（加密格式）
        try:
            return _decrypt_key(raw).strip()
        except Exception:
            # 解密失败 → 可能是旧版明文文件，执行迁移
            try:
                plaintext = raw.decode("utf-8").strip()
            except Exception:
                # 既无法解密也不是合法 UTF-8 → 重新生成
                logger.warning("API Key 文件无法解密或解析，重新生成")
                plaintext = generate_api_key()
            # 加密存储并覆盖
            encrypted = _encrypt_key(plaintext)
            KEY_FILE.write_bytes(encrypted)
            _set_private_permissions(KEY_FILE)
            # 确保 hash 文件存在
            if not KEY_HASH_FILE.exists():
                hashed = bcrypt.hashpw(
                    plaintext.encode("utf-8"), bcrypt.gensalt(rounds=12)
                )
                KEY_HASH_FILE.write_bytes(hashed)
                _set_private_permissions(KEY_HASH_FILE)
            logger.info("检测到明文 API Key 文件，已自动加密迁移")
            return plaintext
    # 全新安装：生成并加密存储
    key = generate_api_key()
    encrypted = _encrypt_key(key)
    KEY_FILE.write_bytes(encrypted)
    hashed = bcrypt.hashpw(key.encode("utf-8"), bcrypt.gensalt(rounds=12))
    KEY_HASH_FILE.write_bytes(hashed)
    _set_private_permissions(KEY_FILE)
    _set_private_permissions(KEY_HASH_FILE)
    return key


def verify_api_key(authorization: str) -> bool:
    """校验 Authorization: Bearer sk-moa-xxx"""
    if not authorization or not authorization.startswith("Bearer "):
        return False
    token = authorization[7:].strip()
    if not KEY_HASH_FILE.exists():
        return False
    stored_hash = KEY_HASH_FILE.read_bytes()
    try:
        # bcrypt.checkpw 自身是常量时间比较
        return bcrypt.checkpw(token.encode("utf-8"), stored_hash)
    except (ValueError, TypeError):
        return False


def regenerate_api_key() -> str:
    """--regenerate-key 触发，生成新 key 并加密替换"""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    key = generate_api_key()
    encrypted = _encrypt_key(key)
    KEY_FILE.write_bytes(encrypted)
    hashed = bcrypt.hashpw(key.encode("utf-8"), bcrypt.gensalt(rounds=12))
    KEY_HASH_FILE.write_bytes(hashed)
    _set_private_permissions(KEY_FILE)
    _set_private_permissions(KEY_HASH_FILE)
    return key


def mask_key(key: str) -> str:
    """mask 显示：sk-moa-xxxx...xxxx"""
    if not key or len(key) < 12:
        return "***"
    return f"{key[:12]}...{key[-4:]}"


def get_current_key() -> str:
    """读取当前明文 key（仅供配置页展示用，自动解密）"""
    if KEY_FILE.exists():
        raw = KEY_FILE.read_bytes()
        try:
            return _decrypt_key(raw).strip()
        except Exception:
            # 降级：尝试明文读取（极端情况）
            try:
                return raw.decode("utf-8").strip()
            except Exception:
                return ""
    return ""


def check_rate_limit(client_ip: str) -> tuple:
    """
    简单内存限流（按 client IP）。
    返回 (allowed: bool, retry_after: int)
    """
    now = time.time()
    bucket = _request_log[client_ip]
    # 清理过期
    while bucket and now - bucket[0] > RATE_LIMIT_WINDOW:
        bucket.popleft()
    if len(bucket) >= RATE_LIMIT_MAX_REQUESTS:
        retry_after = int(RATE_LIMIT_WINDOW - (now - bucket[0])) + 1
        return False, max(retry_after, 1)
    bucket.append(now)
    return True, 0


def _set_private_permissions(path: Path):
    """Windows: icacls 仅当前用户可读写"""
    import subprocess
    try:
        username = os.environ.get("USERNAME") or os.environ.get("USER") or "Administrators"
        subprocess.run(
            ["icacls", str(path), "/inheritance:r",
             "/grant", f"{username}:(R,W)"],
            capture_output=True, check=False,
        )
    except Exception as e:
        # 非 Windows 或无权限时记录日志
        logger.warning("设置文件权限失败: %s", str(e)[:100])
