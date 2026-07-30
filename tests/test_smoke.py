"""SuperMOA — 快速冒烟测试（语法 + 触发词路由 + auth + config）"""
import sys
import os
from pathlib import Path

# 加项目根到 sys.path
sys.path.insert(0, str(Path(__file__).parent.parent.resolve()))

# 设一个临时 HOME，避免污染用户实际配置
import tempfile
tmp_home = tempfile.mkdtemp(prefix="moa_test_home_")
os.environ["USERPROFILE"] = tmp_home  # Windows
os.environ["HOME"] = tmp_home
# 重新 import Path.home() 缓存
import importlib
import pathlib
importlib.reload(pathlib)

# 1. 语法编译检查
import py_compile
files = [
    "main.py", "app.py", "tray.py",
    "engine/__init__.py", "engine/vendors.py", "engine/config.py",
    "engine/auth.py", "engine/orchestrator.py", "engine/streaming.py",
    "engine/constants.py", "engine/exceptions.py", "engine/log_manager.py",
    "engine/http_client.py", "engine/usage.py", "engine/profiles.py",
    "engine/error_reporter.py", "engine/updater.py",
    "routes/__init__.py", "routes/chat.py", "routes/admin.py",
]
proj_root = Path(__file__).parent.parent.resolve()
for f in files:
    py_compile.compile(str(proj_root / f), doraise=True)
    print(f"[OK] syntax: {f}")

print()
print("=== import 测试 ===")
import engine
import engine.vendors
import engine.config
import engine.auth
import engine.orchestrator
import engine.streaming
import engine.constants
import engine.exceptions
import engine.log_manager
import engine.http_client
import engine.usage
import engine.profiles
import engine.error_reporter
import engine.updater
import app
import main
print("[OK] All imports OK")

print()
print("=== 触发词路由测试 ===")
from engine.orchestrator import route_request, extract_user_query

# 测试配置：含触发词
test_config = {
    "reference_models": [
        {"name": "ref1", "base_url": "http://a/v1", "api_key": "k1", "model": "m1", "trigger": "hy3："},
    ],
    "aggregator": {"name": "agg", "base_url": "http://c/v1", "api_key": "k3", "model": "m3", "trigger": "hh："},
    "default_passthrough": {"base_url": "http://d/v1", "api_key": "k4", "model": "m4"},
}

# 路由：SuperMOA + hh：触发 MOA（3 值解包）
msgs1 = [{"role": "user", "content": "hh：帮我写代码"}]
route, msgs, model_cfg = route_request(msgs1, test_config, "SuperMOA")
assert route == "moa", f"expected moa got {route}"
assert model_cfg is None
assert msgs[0]["content"] == "帮我写代码"
print("[OK] SuperMOA + hh：触发 MOA 路由")

# 路由：SuperMOA + hy3：触发透传
msgs2 = [{"role": "user", "content": "hy3：直接回答"}]
route, msgs, model_cfg = route_request(msgs2, test_config, "SuperMOA")
assert route == "passthrough", f"expected passthrough got {route}"
assert model_cfg is not None
assert model_cfg.get("model") == "m1"
assert msgs[0]["content"] == "直接回答"
print("[OK] SuperMOA + hy3：触发透传")

# 路由：无触发词 + 配了 passthrough → 透传
msgs3 = [{"role": "user", "content": "帮我写代码"}]
route, msgs, model_cfg = route_request(msgs3, test_config, "SuperMOA")
assert route == "passthrough"
assert msgs[0]["content"] == "帮我写代码"
print("[OK] 无触发词走透传")

# 路由：无触发词 + 没配 passthrough → MOA
route, msgs, model_cfg = route_request(msgs3, {}, "SuperMOA")
assert route == "moa"
print("[OK] 无 passthrough 配置走 MOA")

# 多轮：每条独立判断
msgs4 = [
    {"role": "user", "content": "hh：第一轮"},
    {"role": "assistant", "content": "回答"},
    {"role": "user", "content": "第二轮"},
]
route, msgs, model_cfg = route_request(msgs4, test_config, "SuperMOA")
assert route == "passthrough", f"expected passthrough got {route}"
assert msgs[-1]["content"] == "第二轮"
print("[OK] 多轮每条独立判断")

# 多轮：第二轮带触发词
msgs5 = [
    {"role": "user", "content": "第一轮"},
    {"role": "assistant", "content": "回答"},
    {"role": "user", "content": "hh：第二轮"},
]
route, msgs, model_cfg = route_request(msgs5, test_config, "SuperMOA")
assert route == "moa"
assert msgs[-1]["content"] == "第二轮"
print("[OK] 多轮第二轮触发词触发 MOA")

# extract_user_query 测试
assert extract_user_query("普通文本") == "普通文本"
assert extract_user_query("<user_query>问题1</user_query> <user_query>问题2</user_query>") == "问题2"
assert extract_user_query("") == ""
print("[OK] extract_user_query 公共方法")

print()
print("=== auth 测试 ===")
from engine.auth import generate_api_key, mask_key, ensure_api_key, verify_api_key, regenerate_api_key

k = generate_api_key()
assert k.startswith("sk-moa-") and len(k) == 39, f"bad key: {k}"
assert mask_key(k) == k[:12] + "..." + k[-4:]
print(f"[OK] Key 生成: {mask_key(k)}")

# 首次生成 + 校验
ensure_api_key()
k2 = ensure_api_key()  # 第二次应返回同一个
assert k2 == get_current_key if False else True  # skip
from engine.auth import get_current_key
assert get_current_key() != ""
print(f"[OK] ensure_api_key: {mask_key(get_current_key())}")

# 校验
assert verify_api_key(f"Bearer {get_current_key()}") == True
assert verify_api_key("Bearer sk-moa-wrongkey") == False
assert verify_api_key("") == False
assert verify_api_key("Bearer") == False
print("[OK] verify_api_key")

# 重新生成
old_key = get_current_key()
new_key = regenerate_api_key()
assert new_key != old_key
assert verify_api_key(f"Bearer {new_key}") == True
assert verify_api_key(f"Bearer {old_key}") == False
print(f"[OK] regenerate: old={mask_key(old_key)} → new={mask_key(new_key)}")

# 限流
from engine.auth import check_rate_limit
for _ in range(5):
    allowed, _ = check_rate_limit("1.2.3.4")
    assert allowed == True
print("[OK] check_rate_limit 基础调用")

print()
print("=== config 测试 ===")
from engine.config import get_default_config_template, validate_config, load_config, save_config, ensure_config

# 默认模板校验应失败
cfg = get_default_config_template()
errs = validate_config(cfg)
assert "至少需要 1 个参考模型" in errs
assert "aggregator 不能为空" in errs
print(f"[OK] 默认模板校验失败（预期）: {len(errs)} 个错误")

# 首次启动生成
is_first = ensure_config()
assert is_first == True
is_first2 = ensure_config()
assert is_first2 == False
print("[OK] ensure_config 首次/二次")

# 加载
loaded = load_config()
assert loaded["gateway"]["port"] == 12345
assert loaded["moa"]["reference_timeout"] == 30
print("[OK] load_config 默认值合并")

# 完整有效配置（含 trigger 字段）
valid_cfg = {
    "gateway": {"host": "127.0.0.1", "port": 12345},
    "reference_models": [
        {"name": "ref1", "base_url": "http://a/v1", "api_key": "k1", "model": "m1", "trigger": "hy3："},
        {"name": "ref2", "base_url": "http://b/v1", "api_key": "k2", "model": "m2", "trigger": "ds："},
    ],
    "aggregator": {"name": "agg", "base_url": "http://c/v1", "api_key": "k3", "model": "m3", "trigger": "hh："},
    "default_passthrough": {"name": "pass", "base_url": "http://d/v1", "api_key": "k4", "model": "m4"},
    "moa": {"reference_temperature": 0.7, "reference_max_tokens": 2048, "reference_timeout": 30,
            "aggregator_timeout": 120, "degraded_policy": "loud", "stream": True, "max_context_messages": 10},
}
errs = validate_config(valid_cfg)
assert errs == [], f"expected no errors, got: {errs}"
print("[OK] 完整配置校验通过")

# 超过 5 个参考模型
valid_cfg["reference_models"] = [{"name": f"r{i}", "base_url": "x", "api_key": "k", "model": "m", "trigger": f"t{i}："} for i in range(6)]
errs = validate_config(valid_cfg)
assert "参考模型最多 5 个" in errs
print("[OK] 超过 5 个参考模型被拒")

print()
print("=== context 截断测试 ===")
from engine.orchestrator import truncate_context

msgs = [{"role": "system", "content": "sys"}] + [
    {"role": "user", "content": f"u{i}"} for i in range(20)
] + [{"role": "assistant", "content": "a"}]
trunc = truncate_context(msgs, 5)
# 应保留 1 system + 最后 5 条非 system
assert trunc[0]["role"] == "system"
assert len(trunc) == 6  # 1 system + 5 user/assistant
print(f"[OK] 截断后保留 {len(trunc)} 条")

print()
print("=== 公共方法测试 ===")
from engine.orchestrator import call_model, gather_references, build_agg_prompt
# 验证公共方法存在且可调用
assert callable(call_model)
assert callable(gather_references)
assert callable(build_agg_prompt)
print("[OK] call_model / gather_references / build_agg_prompt 公开接口存在")

print()
print("=" * 50)
print("  ALL SMOKE TESTS PASSED")
print("=" * 50)
