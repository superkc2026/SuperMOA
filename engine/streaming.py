"""SuperMOA — 流式输出（含透传 stream + MOA stream + fallback 伪造 SSE）

公共接口：
  - passthrough_stream(): 透传上游 SSE
  - moa_round_stream(): MOA 流式输出
"""
import asyncio
import json
import logging
import uuid
from typing import AsyncGenerator, Optional, List, Dict

import httpx

from engine.orchestrator import gather_references, build_agg_prompt, call_model, truncate_context
from engine.orchestrator import _extract_text, extract_user_query
from engine.health import is_model_healthy
from engine.exceptions import (
    UpstreamError,
    NoHealthyReferenceError,
    AllReferencesFailedError,
    AggregatorNotConfiguredError,
    StreamError,
    friendly_error_message,
)
from engine import constants as C
from engine.http_client import get_client

logger = logging.getLogger("supermoa")


# ============================================================
# 透传流式
# ============================================================

async def passthrough_stream(
    messages: List[Dict],
    model_cfg: dict,
    client_params: Optional[dict] = None,
) -> AsyncGenerator[str, None]:
    """透传上游 SSE，逐 chunk 转发，传递所有客户端参数（含 tools 等）。

    Args:
        messages: 消息列表
        model_cfg: 模型配置 dict
        client_params: 客户端参数

    Yields:
        SSE 格式的字符串行
    """
    client_params = client_params or {}
    temp = client_params.get("temperature", C.DEFAULT_REFERENCE_TEMPERATURE)
    max_tokens = client_params.get("max_tokens", C.DEFAULT_AGGREGATOR_MAX_TOKENS)

    model_name = model_cfg.get("model", "")
    base_url = model_cfg.get("base_url", "")
    api_key = model_cfg.get("api_key", "")

    payload = {
        "model": model_name,
        "messages": messages,
        "temperature": temp,
        "stream": True,
        "max_tokens": max_tokens,
    }
    # 传递额外参数（tools, tool_choice 等）
    for k, v in client_params.items():
        if k not in payload and v is not None:
            payload[k] = v
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    url = f"{base_url.rstrip('/')}/chat/completions"

    try:
        client = get_client(C.DEFAULT_HTTP_TIMEOUT)
        async with client.stream("POST", url, json=payload, headers=headers) as resp:
            if resp.status_code != 200:
                body = await resp.aread()
                err = body.decode("utf-8", errors="replace")[:C.PREVIEW_MAX_LENGTH]
                logger.error("透传上游返回 %d: %s", resp.status_code, err)
                friendly_msg = friendly_error_message(err, resp.status_code)
                yield _error_sse(resp.status_code, friendly_msg)
                return
            async for line in resp.aiter_lines():
                if line:
                    yield f"{line}\n\n"
    except httpx.RequestError as e:
        logger.error("透传请求失败: model=%s error=%s", model_name, str(e)[:C.ERROR_MESSAGE_MAX_LENGTH])
        friendly_msg = friendly_error_message(f"{type(e).__name__}: {str(e)[:C.ERROR_MESSAGE_MAX_LENGTH]}")
        yield _error_sse(502, friendly_msg)


# ============================================================
# MOA 流式
# ============================================================

async def moa_round_stream(
    messages: List[Dict],
    config: dict,
    client_params: Optional[dict] = None,
) -> AsyncGenerator[str, None]:
    """MOA 流式输出。

    1. 参考模型非流式并行调用（通过 gather_references 公共方法）
    2. 构造聚合 prompt（通过 build_agg_prompt 公共方法）
    3. 聚合模型流式调用，逐 token SSE
    4. 若聚合模型不支持 stream，fallback 到非流式 + 伪造 SSE

    Args:
        messages: 消息列表
        config: 全局配置
        client_params: 客户端参数

    Yields:
        SSE 格式的字符串行
    """
    client_params = client_params or {}
    moa_cfg = config.get("moa", {})

    # 截断 context
    truncated = truncate_context(messages, moa_cfg.get("max_context_messages", C.DEFAULT_MAX_CONTEXT_MESSAGES))

    # 1. 参考模型并行（公共方法）
    try:
        references, healthy_refs = await gather_references(truncated, config, client_params)
    except NoHealthyReferenceError as e:
        yield _error_sse(502, str(e))
        return
    except AllReferencesFailedError as e:
        yield _error_sse(502, str(e))
        return
    except Exception as e:
        logger.error("参考模型调度失败: %s", str(e)[:C.ERROR_MESSAGE_MAX_LENGTH])
        friendly_msg = friendly_error_message(f"参考模型调度失败: {type(e).__name__}: {str(e)[:C.ERROR_MESSAGE_MAX_LENGTH]}")
        yield _error_sse(502, friendly_msg)
        return

    # 2. 构造聚合 prompt（公共方法）
    try:
        agg_messages = build_agg_prompt(references, config, truncated)
    except AggregatorNotConfiguredError as e:
        yield _error_sse(502, str(e))
        return

    # 3. 流式调用聚合模型
    agg = config["aggregator"]
    agg_timeout = moa_cfg.get("aggregator_timeout", C.AGGREGATOR_TIMEOUT)
    agg_temp = client_params.get("temperature", agg.get("temperature", C.DEFAULT_AGGREGATOR_TEMPERATURE))
    agg_max_tokens = client_params.get("max_tokens", agg.get("max_tokens", C.DEFAULT_AGGREGATOR_MAX_TOKENS))

    model_name = agg.get("model", "")
    base_url = agg.get("base_url", "")
    api_key = agg.get("api_key", "")

    payload = {
        "model": model_name,
        "messages": agg_messages,
        "temperature": agg_temp,
        "stream": True,
        "max_tokens": agg_max_tokens,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    url = f"{base_url.rstrip('/')}/chat/completions"

    try:
        stream_client = get_client(agg_timeout)
        async with stream_client.stream("POST", url, json=payload, headers=headers) as resp:
            if resp.status_code != 200:
                body = await resp.aread()
                err = body.decode("utf-8", errors="replace")[:C.PREVIEW_MAX_LENGTH]
                friendly_msg = friendly_error_message(err, resp.status_code)
                raise StreamError(friendly_msg)

            has_yielded_data = False
            async for line in resp.aiter_lines():
                if line:
                    yield f"{line}\n\n"
                    if line.startswith("data: ") and not line.startswith("data: [DONE]"):
                        has_yielded_data = True

            if not has_yielded_data:
                raise StreamError("聚合模型未返回流式数据")
    except (StreamError, httpx.RequestError, httpx.HTTPStatusError) as e:
        logger.warning("聚合模型流式失败，尝试 fallback 非流式: %s", str(e)[:C.ERROR_MESSAGE_MAX_LENGTH])
        # fallback: 非流式调用 + 伪造 SSE（使用全局连接池）
        try:
            fallback_client = get_client(agg_timeout)
            agg_content, _, _ = await call_model(
                fallback_client, agg, agg_messages, agg_temp, agg_max_tokens
            )
            yield _fake_sse(agg_content, agg.get("model", "moa"))
        except UpstreamError as e2:
            logger.error("聚合模型 fallback 也失败: %s", str(e2)[:C.ERROR_MESSAGE_MAX_LENGTH_LONG])
            friendly_msg = friendly_error_message(str(e2)[:C.ERROR_MESSAGE_MAX_LENGTH_LONG])
            yield _error_sse(502, friendly_msg)
        except Exception as e2:
            logger.error("聚合模型 fallback 意外错误: %s", str(e2)[:C.ERROR_MESSAGE_MAX_LENGTH_LONG])
            friendly_msg = friendly_error_message(f"{type(e2).__name__}: {str(e2)[:C.ERROR_MESSAGE_MAX_LENGTH_LONG]}")
            yield _error_sse(502, friendly_msg)


# ============================================================
# SSE 工具
# ============================================================

def _fake_sse(content: str, model: str) -> str:
    """把非流式结果包装成单 chunk SSE 流。

    Args:
        content: 非流式返回的内容
        model: 模型名称

    Returns:
        SSE 格式的字符串（包含 content chunk + stop chunk + [DONE]）
    """
    chat_id = f"moa-{uuid.uuid4().hex[:8]}"
    chunk1 = {
        "id": chat_id,
        "object": "chat.completion.chunk",
        "created": _now_ts(),
        "model": model,
        "choices": [{"index": 0, "delta": {"role": "assistant", "content": content}, "finish_reason": None}],
    }
    chunk2 = {
        "id": chat_id,
        "object": "chat.completion.chunk",
        "created": _now_ts(),
        "model": model,
        "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
    }
    return (
        f"data: {json.dumps(chunk1, ensure_ascii=False)}\n\n"
        f"data: {json.dumps(chunk2, ensure_ascii=False)}\n\n"
        f"data: [DONE]\n\n"
    )


def _error_sse(status: int, message: str) -> str:
    """错误 SSE（OpenAI 兼容错误格式）。

    Args:
        status: HTTP 状态码
        message: 错误消息

    Returns:
        SSE 格式的错误字符串
    """
    err = {
        "error": {
            "message": message,
            "type": "upstream_error",
            "code": status,
        }
    }
    return f"data: {json.dumps(err, ensure_ascii=False)}\n\ndata: [DONE]\n\n"


def _now_ts() -> int:
    """返回当前 Unix 时间戳（秒）。"""
    import time
    return int(time.time())
