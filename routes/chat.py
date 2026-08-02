"""SuperMOA — /v1/chat/completions 端点 + 路由执行"""
import logging
import uuid
import time

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse

from engine.auth import verify_api_key, check_rate_limit
from engine.config import load_config
from engine.orchestrator import route_request, moa_round, passthrough
from engine.orchestrator import extract_user_query, _extract_text
from engine.streaming import moa_round_stream, passthrough_stream
from engine.exceptions import error_response

logger = logging.getLogger("supermoa")

router = APIRouter()

# 幂等缓存：request_id → response（5 分钟过期）
_idempotency_cache: dict = {}
_IDEMPOTENCY_TTL = 300  # 5 分钟


@router.post("/v1/chat/completions")
async def chat_completions(request: Request):
    """OpenAI 兼容的 chat completions 端点。

    1. API Key 校验
    2. 限流
    3. 解析 body
    4. 路由决策（触发词）
    5. 记录日志
    6. 执行（流式/非流式）
    """
    from app import _log_request, _identify_client

    # 1. API Key 校验
    auth = request.headers.get("authorization", "")
    if not verify_api_key(auth):
        return JSONResponse(
            {"error": {"message": "Invalid API Key", "type": "auth_error", "code": 401}},
            status_code=401,
        )

    # 2. 限流（按 client IP）
    if request.client:
        allowed, retry_after = check_rate_limit(request.client.host)
        if not allowed:
            return JSONResponse(
                {"error": {"message": f"请求过于频繁，请 {retry_after} 秒后重试", "type": "rate_limit", "code": 429}},
                status_code=429,
                headers={"Retry-After": str(retry_after)},
            )

    # 3. 解析 body
    try:
        body = await request.json()
    except (ValueError, RuntimeError) as e:
        logger.warning("JSON body 解析失败: %s", str(e)[:100])
        return JSONResponse(
            error_response(400, "请求体 JSON 格式错误", "invalid_request"),
            status_code=400,
        )

    # 3.5 幂等检查（如果客户端传了 request_id）
    request_id = body.get("request_id") or body.get("user") or ""
    if request_id:
        # 清理过期缓存
        now = time.time()
        expired = [k for k, v in _idempotency_cache.items() if now - v["ts"] > _IDEMPOTENCY_TTL]
        for k in expired:
            del _idempotency_cache[k]
        # 检查重复
        cache_key = f"{request_id}:{hash(str(body.get('messages', ''))[:200])}"
        if cache_key in _idempotency_cache:
            cached = _idempotency_cache[cache_key]
            logger.info("幂等命中: request_id=%s, 返回缓存结果", request_id[:50])
            return JSONResponse(cached["response"])

    messages = body.get("messages", []) or []
    stream = bool(body.get("stream", False))
    client_params = {}
    for k in ("temperature", "max_tokens", "top_p", "tools", "tool_choice", "response_format", "frequency_penalty", "presence_penalty", "stop", "seed"):
        if k in body and body[k] is not None:
            client_params[k] = body[k]

    # 4. 路由（model 字段 + 触发词）
    config = load_config()
    model_name = body.get("model", "")
    route, processed_messages, model_cfg = route_request(messages, config, model_name)

    # 记录请求日志
    actual_model = "SuperMOA" if route == "moa" else (model_cfg or {}).get("model", "?")
    original_prompt = ""
    for m in reversed(messages):
        if m.get("role") == "user":
            raw_content = m.get("content", "")
            original_prompt = _extract_text(raw_content)
            break
    # 提取触发词
    prefix = ""
    _check_text = extract_user_query(original_prompt)
    all_triggers = []
    agg_cfg = config.get("aggregator")
    if agg_cfg and agg_cfg.get("trigger"):
        all_triggers.append(agg_cfg["trigger"])
    for ref in (config.get("reference_models") or []):
        if ref.get("trigger"):
            all_triggers.append(ref["trigger"])
    all_triggers.sort(key=len, reverse=True)
    for t in all_triggers:
        if t in _check_text:
            prefix = t
            break
    preview = extract_user_query(original_prompt)
    client = _identify_client(request.headers.get("user-agent", ""), model_name)
    _user_count = sum(1 for m in messages if m.get("role") == "user")
    _has_assistant = any(m.get("role") == "assistant" for m in messages)
    _is_user_msg = (_user_count <= 1 and not _has_assistant)
    _log_request(model_name, route, actual_model, prefix, preview, client, is_user_message=_is_user_msg)

    # 5. 执行
    try:
        if stream:
            return StreamingResponse(
                _route_stream(route, processed_messages, config, client_params, model_cfg),
                media_type="text/event-stream",
                headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
            )
        return await _route_nonstream(route, processed_messages, config, client_params, model_cfg)
    except Exception as e:
        from engine.exceptions import friendly_error_message
        friendly_msg = friendly_error_message(f"{type(e).__name__}: {str(e)[:300]}")
        return JSONResponse(
            error_response(502, friendly_msg, "upstream_error"),
            status_code=502,
        )


async def _route_nonstream(route: str, messages, config, client_params, model_cfg=None):
    """非流式路由执行"""
    if route == "passthrough":
        cfg = model_cfg or config["default_passthrough"]
        content, usage, tool_calls = await passthrough(messages, cfg, client_params)
        model_name = cfg.get("model", "passthrough")
    else:
        content, usage = await moa_round(messages, config, client_params)
        tool_calls = None
        model_name = "SuperMOA"

    # 记录用量统计
    _record_usage(route, model_name, usage, client_params.get("client", ""))

    msg = {"role": "assistant", "content": content}
    if tool_calls:
        msg["tool_calls"] = tool_calls
    return {
        "id": f"moa-{uuid.uuid4().hex[:8]}",
        "object": "chat.completion",
        "model": model_name,
        "choices": [{
            "index": 0,
            "message": msg,
            "finish_reason": "tool_calls" if tool_calls else "stop",
        }],
        "usage": usage,
    }


async def _route_stream(route: str, messages, config, client_params, model_cfg=None):
    """流式路由执行"""
    if route == "passthrough":
        cfg = model_cfg or config["default_passthrough"]
        async for chunk in passthrough_stream(messages, cfg, client_params):
            yield chunk
    else:
        async for chunk in moa_round_stream(messages, config, client_params):
            yield chunk


def _record_usage(route: str, model_name: str, usage: dict, client: str) -> None:
    """记录用量统计（非流式）"""
    try:
        from engine.usage import record_usage, calculate_cost
        from engine.config import load_config

        prompt_tokens = usage.get("prompt_tokens", 0) if usage else 0
        completion_tokens = usage.get("completion_tokens", 0) if usage else 0

        # 从配置中查找 base_url 来计算成本
        config = load_config()
        base_url = ""
        for ref in (config.get("reference_models") or []):
            if ref.get("model") == model_name:
                base_url = ref.get("base_url", "")
                break
        agg = config.get("aggregator")
        if agg and agg.get("model") == model_name:
            base_url = agg.get("base_url", "")
        dp = config.get("default_passthrough")
        if dp and dp.get("model") == model_name:
            base_url = dp.get("base_url", "")

        cost = calculate_cost(model_name, base_url, prompt_tokens, completion_tokens)
        record_usage(model_name, route, prompt_tokens, completion_tokens, cost, client)
    except Exception as e:
        logger.debug("用量记录失败: %s", str(e)[:100])
