"""SuperMOA — 全局常量定义（消除魔法数字）

所有超时、限流、最大日志数等硬编码值集中在此文件管理。
"""
from datetime import timedelta

# ============================================================
# 网络超时（秒）
# ============================================================
DEFAULT_HTTP_TIMEOUT = 120          # 默认 HTTP 客户端超时
REFERENCE_MODEL_TIMEOUT = 30         # 参考模型调用超时
AGGREGATOR_TIMEOUT = 120             # 聚合模型调用超时
HEALTH_CHECK_TIMEOUT = 10            # 健康检查 ping 超时
TEST_CONNECTION_TIMEOUT = 15         # 测试连通性超时
ERROR_MESSAGE_MAX_LENGTH = 200       # 错误消息截断长度
ERROR_MESSAGE_MAX_LENGTH_LONG = 300  # 长错误消息截断长度
PREVIEW_MAX_LENGTH = 500             # SSE 错误响应 body 截断长度

# ============================================================
# MOA 引擎参数
# ============================================================
DEFAULT_REFERENCE_TEMPERATURE = 0.7   # 参考模型默认温度
DEFAULT_AGGREGATOR_TEMPERATURE = 0.3  # 聚合模型默认温度
DEFAULT_REFERENCE_MAX_TOKENS = 2048   # 参考模型默认 max_tokens
DEFAULT_AGGREGATOR_MAX_TOKENS = 4096  # 聚合模型默认 max_tokens
DEFAULT_MAX_CONTEXT_MESSAGES = 10     # 上下文截断保留的最大消息数

# ============================================================
# 重试与健康检查
# ============================================================
MAX_RETRIES = 1                       # 参考模型失败重试次数
HEALTH_CHECK_INTERVAL = 300           # 健康检查间隔（秒）

# ============================================================
# 请求日志
# ============================================================
MAX_REQUEST_LOGS = 100                # 内存中保留的最大日志条数
LOG_PREVIEW_LENGTH = 50               # 日志预览截断长度（短）
LOG_PREVIEW_FULL_LENGTH = 200         # 日志预览截断长度（长）
LOG_DEDUP_WINDOW_SECONDS = 10         # 日志去重时间窗口（秒）
LOG_ROTATION_MAX_SIZE = 10 * 1024 * 1024  # 日志文件轮转阈值（10MB）
LOG_ROTATION_KEEP_FILES = 3           # 轮转保留的历史文件数

# ============================================================
# 限流
# ============================================================
RATE_LIMIT_WINDOW = 60                # 限流时间窗口（秒）
RATE_LIMIT_MAX_REQUESTS = 60          # 每窗口最大请求数

# ============================================================
# 模型限制
# ============================================================
MAX_REFERENCE_MODELS = 5              # 最大参考模型数
MIN_REFERENCE_MODELS = 1              # 最小参考模型数

# ============================================================
# 端口范围
# ============================================================
MIN_PORT = 1
MAX_PORT = 65535
DEFAULT_PORT = 12345
DEFAULT_HOST = "127.0.0.1"

# ============================================================
# 品牌标识
# ============================================================
BRAND_NAME = "SuperMOA"
BRAND_DESC = "多模型聚合推理系统"
DEFAULT_TRIGGER_SUFFIX = "："  # 中文全角冒号作为触发词后缀
DEFAULT_AGGREGATOR_TRIGGER = "hh："

# ============================================================
# 版本号
# ============================================================
VERSION = "1.0.0"                     # 当前版本（用于更新检查）

# ============================================================
# 版本更新检查（腾讯云 COS）
# ============================================================
# versions.json 地址（COS 根目录），格式：
# {
#   "latest": "1.0.0",
#   "release_date": "2026-07-30",
#   "releases": {
#     "1.0.0": {
#       "download_url": "https://supermoa-release-XXXXX.cos.ap-shanghai.myqcloud.com/v1.0.0/SuperMOA.exe",
#       "sha256": "abc123...",
#       "release_notes": "首个开源版本",
#       "min_required_version": null
#     }
#   }
# }
VERSIONS_URL = "https://workbuddy-d5gwqm9e703087bdc-1449269205.tcloudbaseapp.com/versions.json"
UPDATE_CHECK_TIMEOUT = 15             # 版本检查 HTTP 请求超时（秒）
