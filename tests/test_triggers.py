"""SuperMOA — 触发词路由测试（≥10 用例）

覆盖：
1. SuperMOA + hh 触发 → MOA
2. SuperMOA + hy3 触发 → 透传
3. 无触发词 + 有透传配置 → 透传
4. 无触发词 + 无透传配置 → MOA
5. user_query 标签提取（取最后一个）
6. 最长触发词优先匹配
7. 触发词在中间（in 搜索保留现状）
8. model_name=None → 默认路由
9. model_name 小写 "supermoa"
10. 空 messages
11. content 多模态 list 格式
12. 多轮对话每条独立判断
"""
import sys
import os
from pathlib import Path

# 加项目根到 sys.path
sys.path.insert(0, str(Path(__file__).parent.parent.resolve()))

# 设一个临时 HOME，避免污染用户实际配置
import tempfile
tmp_home = tempfile.mkdtemp(prefix="moa_trigger_test_")
os.environ["USERPROFILE"] = tmp_home
os.environ["HOME"] = tmp_home
import importlib
import pathlib
importlib.reload(pathlib)

from engine.orchestrator import route_request, extract_user_query


# 测试用配置
def make_config():
    return {
        "reference_models": [
            {"name": "ref1", "base_url": "http://a/v1", "api_key": "k1", "model": "m1", "trigger": "hy3："},
            {"name": "ref2", "base_url": "http://b/v1", "api_key": "k2", "model": "m2", "trigger": "ds："},
        ],
        "aggregator": {"name": "agg", "base_url": "http://c/v1", "api_key": "k3", "model": "m3", "trigger": "hh："},
        "default_passthrough": {"name": "pass", "base_url": "http://d/v1", "api_key": "k4", "model": "m4"},
    }


def make_config_no_passthrough():
    cfg = make_config()
    del cfg["default_passthrough"]
    return cfg


# ============================================================
# 测试用例
# ============================================================

def test_1_supermoa_hh_triggers_moa():
    """1. SuperMOA + hh：触发词 → MOA"""
    config = make_config()
    msgs = [{"role": "user", "content": "hh：帮我写代码"}]
    route, processed, model_cfg = route_request(msgs, config, "SuperMOA")
    assert route == "moa", f"expected moa, got {route}"
    assert model_cfg is None
    assert processed[0]["content"] == "帮我写代码"
    print("[OK] 1. SuperMOA + hh：触发 MOA")


def test_2_supermoa_hy3_triggers_passthrough():
    """2. SuperMOA + hy3：触发词 → 透传到 ref1"""
    config = make_config()
    msgs = [{"role": "user", "content": "hy3：直接回答"}]
    route, processed, model_cfg = route_request(msgs, config, "SuperMOA")
    assert route == "passthrough", f"expected passthrough, got {route}"
    assert model_cfg is not None
    assert model_cfg.get("model") == "m1"
    assert processed[0]["content"] == "直接回答"
    print("[OK] 2. SuperMOA + hy3：触发透传")


def test_3_no_trigger_with_passthrough():
    """3. 无触发词 + 有透传配置 → 透传"""
    config = make_config()
    msgs = [{"role": "user", "content": "普通消息"}]
    route, processed, model_cfg = route_request(msgs, config, "SuperMOA")
    assert route == "passthrough", f"expected passthrough, got {route}"
    assert model_cfg is not None
    assert model_cfg.get("model") == "m4"
    assert processed[0]["content"] == "普通消息"
    print("[OK] 3. 无触发词 → 默认透传")


def test_4_no_trigger_no_passthrough():
    """4. 无触发词 + 无透传配置 → MOA"""
    config = make_config_no_passthrough()
    msgs = [{"role": "user", "content": "普通消息"}]
    route, processed, model_cfg = route_request(msgs, config, "SuperMOA")
    assert route == "moa", f"expected moa, got {route}"
    assert model_cfg is None
    assert processed[0]["content"] == "普通消息"
    print("[OK] 4. 无触发词无透传 → MOA")


def test_5_user_query_extraction():
    """5. user_query 标签提取（取最后一个）"""
    text = "历史消息 <user_query>第一个问题</user_query> 中间内容 <user_query>hh：第二个问题</user_query>"
    result = extract_user_query(text)
    assert result == "hh：第二个问题", f"expected 'hh：第二个问题', got '{result}'"
    # 无标签时返回原始文本
    result2 = extract_user_query("普通文本")
    assert result2 == "普通文本"
    # 空文本
    assert extract_user_query("") == ""
    print("[OK] 5. user_query 标签提取")


def test_6_longest_trigger_priority():
    """6. 最长触发词优先匹配"""
    config = {
        "reference_models": [
            {"name": "ref1", "base_url": "http://a/v1", "api_key": "k1", "model": "m1", "trigger": "hy3："},
            {"name": "ref2", "base_url": "http://b/v1", "api_key": "k2", "model": "m2", "trigger": "hy3-extra："},
        ],
        "aggregator": {"name": "agg", "base_url": "http://c/v1", "api_key": "k3", "model": "m3", "trigger": "hh："},
    }
    msgs = [{"role": "user", "content": "hy3-extra：长触发词测试"}]
    route, processed, model_cfg = route_request(msgs, config, "SuperMOA")
    assert route == "passthrough"
    assert model_cfg is not None
    assert model_cfg.get("model") == "m2", f"expected m2 (longer trigger), got {model_cfg.get('model')}"
    assert processed[0]["content"] == "长触发词测试"
    print("[OK] 6. 最长触发词优先匹配")


def test_7_trigger_in_middle():
    """7. 触发词在中间（in 搜索保留现状，不要求 startswith）"""
    config = make_config()
    # 触发词在文本中间，仍能被 in 搜索匹配
    msgs = [{"role": "user", "content": "前缀文字 hh：后缀内容"}]
    route, processed, model_cfg = route_request(msgs, config, "SuperMOA")
    assert route == "moa", f"expected moa (in search), got {route}"
    # 触发词被替换掉，剩余 "前缀文字 后缀内容"
    assert "hh：" not in processed[0]["content"]
    assert "后缀内容" in processed[0]["content"]
    print("[OK] 7. 触发词在中间（in 搜索）")


def test_8_model_name_none():
    """8. model_name=None → 默认路由（走透传）"""
    config = make_config()
    msgs = [{"role": "user", "content": "普通消息"}]
    route, processed, model_cfg = route_request(msgs, config, None)
    # model_name=None 不匹配 SuperMOA，走默认透传
    assert route == "passthrough", f"expected passthrough, got {route}"
    print("[OK] 8. model_name=None → 默认透传")


def test_9_model_name_lowercase_supermoa():
    """9. model_name 小写 'supermoa' → 正常识别"""
    config = make_config()
    msgs = [{"role": "user", "content": "hh：小写测试"}]
    route, processed, model_cfg = route_request(msgs, config, "supermoa")
    assert route == "moa", f"expected moa, got {route}"
    assert processed[0]["content"] == "小写测试"
    print("[OK] 9. model_name 小写 'supermoa' 识别")


def test_10_empty_messages():
    """10. 空 messages → 默认路由"""
    config = make_config()
    route, processed, model_cfg = route_request([], config, "SuperMOA")
    assert route == "passthrough", f"expected passthrough for empty msgs, got {route}"
    assert processed == []
    print("[OK] 10. 空 messages → 默认透传")


def test_11_multimodal_content_list():
    """11. content 多模态 list 格式"""
    config = make_config()
    msgs = [{"role": "user", "content": [
        {"type": "text", "text": "hh：多模态测试"},
        {"type": "image_url", "image_url": {"url": "http://example.com/img.png"}},
    ]}]
    route, processed, model_cfg = route_request(msgs, config, "SuperMOA")
    assert route == "moa", f"expected moa for multimodal, got {route}"
    # 触发词被剥离，剩余文本
    content = processed[0]["content"]
    if isinstance(content, str):
        assert "hh：" not in content
    print("[OK] 11. 多模态 content list 格式")


def test_12_multi_turn_independent():
    """12. 多轮对话每条独立判断"""
    config = make_config()
    msgs = [
        {"role": "user", "content": "hh：第一轮"},
        {"role": "assistant", "content": "回答"},
        {"role": "user", "content": "第二轮普通"},
    ]
    route, processed, model_cfg = route_request(msgs, config, "SuperMOA")
    # 第二轮无触发词 → 默认透传
    assert route == "passthrough", f"expected passthrough, got {route}"
    assert processed[-1]["content"] == "第二轮普通"
    print("[OK] 12. 多轮独立判断")


def test_13_user_query_with_trigger():
    """13. <user_query> 标签内含触发词"""
    config = make_config()
    msgs = [{"role": "user", "content": "<system>系统提示</system>\n<user_query>hh：标签内触发</user_query>"}]
    route, processed, model_cfg = route_request(msgs, config, "SuperMOA")
    assert route == "moa", f"expected moa, got {route}"
    assert "hh：" not in processed[0]["content"]
    print("[OK] 13. <user_query> 标签内触发词")


def test_14_multiple_triggers_same_text():
    """14. 多个触发词在同一文本中，最长优先"""
    config = make_config()
    # hh： 和 hy3： 都在文本中，hh：更短，但如果 hy3：在前应该匹配 hy3
    # 实际逻辑：按长度降序搜索，先匹配到的胜出
    msgs = [{"role": "user", "content": "hy3：和 hh：都有"}]
    route, processed, model_cfg = route_request(msgs, config, "SuperMOA")
    # hy3： (4 chars) vs hh： (3 chars) → hy3 更长，优先匹配
    assert route == "passthrough", f"expected passthrough (hy3 longer), got {route}"
    assert model_cfg is not None
    assert model_cfg.get("model") == "m1"
    print("[OK] 14. 多触发词最长优先")


# ============================================================
# 主流程
# ============================================================
def main():
    print("=" * 56)
    print("  SuperMOA — 触发词路由测试")
    print("=" * 56)
    print()

    test_1_supermoa_hh_triggers_moa()
    test_2_supermoa_hy3_triggers_passthrough()
    test_3_no_trigger_with_passthrough()
    test_4_no_trigger_no_passthrough()
    test_5_user_query_extraction()
    test_6_longest_trigger_priority()
    test_7_trigger_in_middle()
    test_8_model_name_none()
    test_9_model_name_lowercase_supermoa()
    test_10_empty_messages()
    test_11_multimodal_content_list()
    test_12_multi_turn_independent()
    test_13_user_query_with_trigger()
    test_14_multiple_triggers_same_text()

    print()
    print("=" * 56)
    print("  ALL TRIGGER TESTS PASSED (14/14)")
    print("=" * 56)


if __name__ == "__main__":
    main()
