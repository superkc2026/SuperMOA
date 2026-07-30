"""端到端集成测试

启动 mock 上游 + SuperMOA gateway，验证完整流程：
1. /health
2. API Key 校验
3. 透传模式（无触发词）
4. MOA 模式（带 hh：触发词）
5. 流式响应
6. 配置页 + API
"""
import sys
import os
import json
import uuid
import time
import tempfile
import threading
from pathlib import Path

# 设临时 HOME（必须在 import engine 之前）
tmp_home = tempfile.mkdtemp(prefix="moa_e2e_home_")
os.environ["USERPROFILE"] = tmp_home
os.environ["HOME"] = tmp_home

sys.path.insert(0, str(Path(__file__).parent.parent.resolve()))

import httpx
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse, JSONResponse

from engine.config import save_config
from engine.auth import ensure_api_key, get_current_key

MOCK_PORT = 19999
MOA_PORT = 12345
MOCK_BASE = f"http://127.0.0.1:{MOCK_PORT}/v1"

# ============================================================
# Mock 上游服务
# ============================================================
mock_app = FastAPI()


@mock_app.post("/v1/chat/completions")
async def mock_chat(request: Request):
    body = await request.json()
    stream = body.get("stream", False)
    model = body.get("model", "mock")
    msgs = body.get("messages", [])
    last_user = ""
    for m in reversed(msgs):
        if m.get("role") == "user":
            last_user = m.get("content", "")
            break
    if isinstance(last_user, list):
        last_user = str(last_user)[:50]
    content = f"[MOCK-{model}] 收到: {str(last_user)[:50]}"

    if stream:
        async def gen():
            chat_id = f"chatcmpl-{uuid.uuid4().hex[:8]}"
            chunk1 = {
                "id": chat_id, "object": "chat.completion.chunk", "model": model,
                "choices": [{"index": 0, "delta": {"role": "assistant", "content": content}, "finish_reason": None}],
            }
            chunk2 = {
                "id": chat_id, "object": "chat.completion.chunk", "model": model,
                "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
            }
            yield f"data: {json.dumps(chunk1, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps(chunk2, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"
        return StreamingResponse(gen(), media_type="text/event-stream")

    return {
        "id": f"chatcmpl-{uuid.uuid4().hex[:8]}",
        "object": "chat.completion",
        "model": model,
        "choices": [{"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
    }


@mock_app.get("/health")
async def mock_health():
    return {"status": "ok"}


# ============================================================
# 启动 servers
# ============================================================
def start_servers():
    """在子线程启动 mock + moa"""
    mock_config = uvicorn.Config(
        mock_app, host="127.0.0.1", port=MOCK_PORT,
        log_level="warning", access_log=False,
    )
    mock_server = uvicorn.Server(mock_config)
    mock_thread = threading.Thread(target=mock_server.run, daemon=True)
    mock_thread.start()

    # MOA gateway
    from app import app as moa_app
    moa_config = uvicorn.Config(
        moa_app, host="127.0.0.1", port=MOA_PORT,
        log_level="warning", access_log=False,
    )
    moa_server = uvicorn.Server(moa_config)
    moa_thread = threading.Thread(target=moa_server.run, daemon=True)
    moa_thread.start()

    # 等待启动
    for _ in range(30):
        try:
            r = httpx.get(f"http://127.0.0.1:{MOA_PORT}/health", timeout=1)
            if r.status_code == 200:
                break
        except Exception:
            time.sleep(0.3)
    else:
        raise RuntimeError("MOA server 启动失败")

    return mock_server, moa_server


# ============================================================
# 测试用例
# ============================================================
def setup_config():
    """写入有效配置：3 个参考模型 + 1 聚合 + 1 透传，全部指向 mock"""
    cfg = {
        "gateway": {"host": "127.0.0.1", "port": MOA_PORT},
        "reference_models": [
            {"name": "ref1", "provider": "openai", "base_url": MOCK_BASE, "api_key": "sk-mock-1", "model": "mock-r1", "trigger": "mock-r1："},
            {"name": "ref2", "provider": "openai", "base_url": MOCK_BASE, "api_key": "sk-mock-2", "model": "mock-r2", "trigger": "mock-r2："},
            {"name": "ref3", "provider": "openai", "base_url": MOCK_BASE, "api_key": "sk-mock-3", "model": "mock-r3", "trigger": "mock-r3："},
        ],
        "aggregator": {"name": "agg", "base_url": MOCK_BASE, "api_key": "sk-mock-agg", "model": "mock-agg", "temperature": 0.3, "max_tokens": 4096, "trigger": "hh："},
        "default_passthrough": {"name": "pass", "base_url": MOCK_BASE, "api_key": "sk-mock-pass", "model": "mock-pass"},
        "moa": {
            "reference_temperature": 0.7, "reference_max_tokens": 2048, "reference_timeout": 30,
            "aggregator_timeout": 120, "degraded_policy": "loud", "stream": True, "max_context_messages": 10,
        },
    }
    save_config(cfg)
    ensure_api_key()


def test_health():
    r = httpx.get(f"http://127.0.0.1:{MOA_PORT}/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    print("[OK] /health")


def test_auth_fail():
    # 无 Authorization
    r = httpx.post(f"http://127.0.0.1:{MOA_PORT}/v1/chat/completions", json={"messages": []})
    assert r.status_code == 401, f"expected 401 got {r.status_code}"
    # 错误 key
    r = httpx.post(
        f"http://127.0.0.1:{MOA_PORT}/v1/chat/completions",
        json={"messages": []}, headers={"Authorization": "Bearer sk-moa-wrong"},
    )
    assert r.status_code == 401
    print("[OK] API Key 校验（401）")


def test_passthrough_nonstream():
    """无触发词 → 走透传，非流式"""
    key = get_current_key()
    r = httpx.post(
        f"http://127.0.0.1:{MOA_PORT}/v1/chat/completions",
        json={
            "model": "SuperMOA",
            "messages": [{"role": "user", "content": "你好"}],
            "stream": False,
        },
        headers={"Authorization": f"Bearer {key}"},
        timeout=30,
    )
    assert r.status_code == 200, f"expected 200 got {r.status_code}: {r.text}"
    data = r.json()
    assert "MOCK-mock-pass" in data["choices"][0]["message"]["content"]
    print(f"[OK] 透传非流式: {data['choices'][0]['message']['content'][:60]}")


def test_moa_nonstream():
    """带 hh：触发词 → 走 MOA，非流式"""
    key = get_current_key()
    r = httpx.post(
        f"http://127.0.0.1:{MOA_PORT}/v1/chat/completions",
        json={
            "model": "SuperMOA",
            "messages": [{"role": "user", "content": "hh：帮我分析"}],
            "stream": False,
        },
        headers={"Authorization": f"Bearer {key}"},
        timeout=60,
    )
    assert r.status_code == 200, f"expected 200 got {r.status_code}: {r.text}"
    data = r.json()
    content = data["choices"][0]["message"]["content"]
    # mock 上游不真实聚合，只验证走了聚合模型（mock-agg）+ 触发词被剥离
    assert "MOCK-mock-agg" in content, f"aggregator not called: {content}"
    assert "hh：" not in content, f"trigger not stripped: {content}"
    print(f"[OK] MOA 非流式（hh：剥离+聚合）: {content[:80]}...")


def test_passthrough_stream():
    """无触发词 → 走透传，流式"""
    key = get_current_key()
    with httpx.stream(
        "POST",
        f"http://127.0.0.1:{MOA_PORT}/v1/chat/completions",
        json={
            "model": "SuperMOA",
            "messages": [{"role": "user", "content": "流式测试"}],
            "stream": True,
        },
        headers={"Authorization": f"Bearer {key}"},
        timeout=30,
    ) as r:
        assert r.status_code == 200
        chunks = []
        for line in r.iter_lines():
            if line.startswith("data: "):
                chunks.append(line[6:])
        assert any("MOCK-mock-pass" in c for c in chunks)
        assert chunks[-1] == "[DONE]"
    print(f"[OK] 透传流式: 收到 {len(chunks)} 个 chunk")


def test_moa_stream():
    """带 hh：触发词 → 走 MOA，流式"""
    key = get_current_key()
    with httpx.stream(
        "POST",
        f"http://127.0.0.1:{MOA_PORT}/v1/chat/completions",
        json={
            "model": "SuperMOA",
            "messages": [{"role": "user", "content": "hh：流式 MOA 测试"}],
            "stream": True,
        },
        headers={"Authorization": f"Bearer {key}"},
        timeout=60,
    ) as r:
        assert r.status_code == 200, f"got {r.status_code}"
        chunks = []
        for line in r.iter_lines():
            if line.startswith("data: "):
                chunks.append(line[6:])
        assert chunks[-1] == "[DONE]", f"last chunk not DONE: {chunks[-1]}"
        # 聚合模型的流式输出
        full_content = ""
        for c in chunks[:-1]:
            try:
                d = json.loads(c)
                delta = d.get("choices", [{}])[0].get("delta", {})
                full_content += delta.get("content", "")
            except Exception:
                pass
        assert "MOCK-mock-agg" in full_content, f"aggregator content missing: {full_content[:200]}"
    print(f"[OK] MOA 流式: 收到 {len(chunks)} chunk, 内容含聚合模型输出")


def test_web_config_page():
    """配置页可访问"""
    r = httpx.get(f"http://127.0.0.1:{MOA_PORT}/")
    assert r.status_code == 200
    assert "SuperMOA" in r.text or "MOA" in r.text
    print("[OK] 配置页可访问")

    r = httpx.get(f"http://127.0.0.1:{MOA_PORT}/api/vendors")
    assert r.status_code == 200
    data = r.json()
    assert len(data["vendors"]) == 10
    print(f"[OK] /api/vendors: {len(data['vendors'])} 家厂商")

    r = httpx.get(f"http://127.0.0.1:{MOA_PORT}/api/config")
    assert r.status_code == 200
    cfg = r.json()
    # api_key 应该被 mask（不等于原始 key）
    original_keys = {"sk-mock-1", "sk-mock-2", "sk-mock-3"}
    for ref in cfg["reference_models"]:
        assert ref["api_key"] not in original_keys, f"api_key not masked: {ref['api_key']}"
    print("[OK] /api/config api_key 已 mask")

    r = httpx.get(f"http://127.0.0.1:{MOA_PORT}/api/key")
    assert r.status_code == 200
    data = r.json()
    assert data["key"].startswith("sk-moa-")
    assert "..." in data["masked"]
    print(f"[OK] /api/key: {data['masked']}")


def test_test_connection():
    """测试 /api/test 端点"""
    r = httpx.post(
        f"http://127.0.0.1:{MOA_PORT}/api/test",
        json={"base_url": MOCK_BASE, "api_key": "sk-mock-1", "model": "mock-r1"},
        timeout=20,
    )
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok", f"test failed: {data}"
    print(f"[OK] /api/test: {data.get('preview', '')[:50]}")

    # 测试错误连接
    r = httpx.post(
        f"http://127.0.0.1:{MOA_PORT}/api/test",
        json={"base_url": "http://127.0.0.1:1/v1", "api_key": "wrong", "model": "x"},
        timeout=20,
    )
    data = r.json()
    assert data["status"] == "error"
    print(f"[OK] /api/test 错误连接: {data.get('message', '')[:50]}")


def test_save_config():
    """测试 /api/config 保存"""
    # 先拿当前配置
    r = httpx.get(f"http://127.0.0.1:{MOA_PORT}/api/config")
    cfg = r.json()
    # 修改一个字段后保存
    cfg["moa"]["reference_temperature"] = 0.9
    r = httpx.post(
        f"http://127.0.0.1:{MOA_PORT}/api/config",
        json=cfg,
    )
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
    # 重新加载验证
    r = httpx.get(f"http://127.0.0.1:{MOA_PORT}/api/config")
    new_cfg = r.json()
    assert new_cfg["moa"]["reference_temperature"] == 0.9
    print("[OK] /api/config 保存 + 重载")


def test_multi_turn():
    """多轮对话：第1轮 hh：，第2轮不带"""
    key = get_current_key()
    msgs = [
        {"role": "user", "content": "hh：第一轮"},
        {"role": "assistant", "content": "回答"},
        {"role": "user", "content": "第二轮普通"},
    ]
    r = httpx.post(
        f"http://127.0.0.1:{MOA_PORT}/v1/chat/completions",
        json={"model": "SuperMOA", "messages": msgs, "stream": False},
        headers={"Authorization": f"Bearer {key}"},
        timeout=30,
    )
    assert r.status_code == 200
    data = r.json()
    content = data["choices"][0]["message"]["content"]
    # 第二轮不带 hh：应走透传
    assert "MOCK-mock-pass" in content, f"expected passthrough, got: {content}"
    print(f"[OK] 多轮独立路由: 第2轮走透传 → {content[:60]}")


# ============================================================
# 主流程
# ============================================================
def main():
    print("=" * 56)
    print("  SuperMOA — 端到端集成测试")
    print("=" * 56)
    print(f"  临时 HOME: {tmp_home}")
    print()

    print("[1/10] 写入测试配置...")
    setup_config()

    print("[2/10] 启动 mock + MOA 服务...")
    start_servers()

    print()
    print("=== 测试用例 ===")
    test_health()
    test_auth_fail()
    test_passthrough_nonstream()
    test_moa_nonstream()
    test_passthrough_stream()
    test_moa_stream()
    test_web_config_page()
    test_test_connection()
    test_save_config()
    test_multi_turn()

    print()
    print("=" * 56)
    print("  ALL E2E TESTS PASSED")
    print("=" * 56)


if __name__ == "__main__":
    main()
