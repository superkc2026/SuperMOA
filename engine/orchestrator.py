"""SuperMOA — MOA 编排 + 触发词路由 + 透传

公共接口：
  - route_request(): 路由决策
  - moa_round(): 非流式 MOA 编排
  - passthrough(): 非流式透传
  - call_model(): 调用单个 OpenAI 兼容模型（公开方法）
  - extract_user_query(): 提取 <user_query> 标签内容
  - gather_references(): 并行调用参考模型（公开方法）
  - build_agg_prompt(): 构造聚合 prompt（公开方法）
  - truncate_context(): 上下文截断
"""
import asyncio
import logging
import re
from typing import Tuple, List, Dict, Optional

import httpx

from engine.health import is_model_healthy
from engine.exceptions import (
    UpstreamError,
    NoHealthyReferenceError,
    AllReferencesFailedError,
    AggregatorNotConfiguredError,
    friendly_error_message,
)
from engine import constants as C
from engine.http_client import get_client

logger = logging.getLogger("supermoa")


# ============================================================
# 文本提取工具
# ============================================================

def _extract_text(content) -> str:
    """从 content 提取文本（支持字符串和 OpenAI 多模态列表格式）。

    Args:
        content: 消息内容，可以是 str 或 list（多模态格式）

    Returns:
        提取出的纯文本字符串
    """
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                parts.append(item.get("text", ""))
            elif isinstance(item, str):
                parts.append(item)
        return "".join(parts)
    return str(content) if content else ""


def extract_user_query(text: str) -> str:
    """提取最后一个 <user_query> 标签内容，避免历史消息干扰。

    如果文本中存在 <user_query>...</user_query> 标签，返回最后一个标签的内容。
    如果没有标签，返回原始文本（已 strip）。

    Args:
        text: 原始文本

    Returns:
        提取出的 user_query 内容或原始文本
    """
    if not text:
        return ""
    uq_matches = re.findall(r'<user_query>(.*?)(?:</user_query>|$)', text, re.DOTALL)
    if uq_matches:
        return uq_matches[-1].strip()
    return text.strip()


def _find_last_user_index(messages: List[Dict]) -> Optional[int]:
    """查找最后一条 user 消息的索引。

    Args:
        messages: 消息列表

    Returns:
        最后一条 user 消息的索引，如果没有则返回 None
    """
    for i in range(len(messages) - 1, -1, -1):
        if messages[i].get("role") == "user":
            return i
    return None


# ============================================================
# 路由决策
# ============================================================

def route_request(
    messages: List[Dict],
    config: dict,
    model_name: str = None,
) -> Tuple[str, List[Dict], Optional[dict]]:
    """路由决策：根据 model_name 和触发词决定走 MOA 还是透传。

    路由规则：
    1. model 字段为 "SuperMOA" + 触发词 hh： → 走 MOA 引擎（剥离触发词）
    2. model 字段为 "SuperMOA" + 触发词 hy3： → 透传到对应模型（剥离触发词）
    3. model 字段为 "SuperMOA" + 无触发词 → 默认透传（快、省钱）
    4. model 字段为 "SuperMOA" + 无触发词 + 无透传配置 → 走 MOA
    5. model 字段匹配某个上游模型 → 透传到那个模型

    Args:
        messages: 消息列表
        config: 全局配置 dict
        model_name: 请求中的 model 字段

    Returns:
        (route, processed_messages, model_cfg) 三元组
        route: "moa" 或 "passthrough"
        processed_messages: 处理后的消息列表
        model_cfg: 透传时的模型配置，MOA 时为 None
    """
    # 收集所有上游模型配置
    all_upstream = list(config.get("reference_models") or [])
    if config.get("aggregator"):
        all_upstream.append(config["aggregator"])
    if config.get("default_passthrough"):
        all_upstream.append(config["default_passthrough"])

    # 1. SuperMOA 模式：默认透传，触发词切换
    if model_name and model_name.lower() == "supermoa":
        idx = _find_last_user_index(messages)
        if idx is not None:
            content_text = _extract_text(messages[idx].get("content", ""))
            # 提取最后一个 <user_query> 标签内容
            content_text = extract_user_query(content_text)
            if content_text:
                # 从配置构建触发词列表（用户自定义触发词，含冒号）
                trigger_pairs: List[Tuple[str, str, Optional[dict]]] = []
                agg = config.get("aggregator")
                if agg and agg.get("trigger"):
                    trigger_pairs.append((agg["trigger"], "moa", None))
                for ref in (config.get("reference_models") or []):
                    if ref.get("trigger"):
                        trigger_pairs.append((ref["trigger"], "passthrough", ref))
                # 在文本里搜索触发词（按长度降序，优先匹配长的）
                trigger_pairs.sort(key=lambda x: len(x[0]), reverse=True)
                for trigger_text, target_type, cfg in trigger_pairs:
                    if trigger_text in content_text:
                        rest = content_text.replace(trigger_text, "", 1)
                        rest = rest.strip()
                        new_msgs = list(messages)
                        new_msgs[idx] = {**messages[idx], "content": rest}
                        if target_type == "moa":
                            logger.info("路由: MOA (触发词: %s)", trigger_text)
                            return "moa", new_msgs, None
                        else:
                            logger.info("路由: passthrough (触发词: %s, model: %s)", trigger_text, cfg.get("model", "?"))
                            return "passthrough", new_msgs, cfg
        # 无触发词 → 默认透传
        if config.get("default_passthrough"):
            logger.info("路由: passthrough (默认, model: %s)", config["default_passthrough"].get("model", "?"))
            return "passthrough", messages, config["default_passthrough"]
        # 没配透传 → 走 MOA
        logger.info("路由: MOA (无透传配置)")
        return "moa", messages, None

    # 2. model 字段精确匹配某个上游模型 → 透传
    if model_name:
        for m in all_upstream:
            if m.get("model") == model_name:
                logger.info("路由: passthrough (模型匹配: %s)", model_name)
                return "passthrough", messages, m

    # 3. 默认透传
    if config.get("default_passthrough"):
        logger.info("路由: passthrough (默认)")
        return "passthrough", messages, config["default_passthrough"]

    # 4. 都没有 → MOA
    logger.info("路由: MOA (默认)")
    return "moa", messages, None


# ============================================================
# MOA 编排
# ============================================================

async def gather_references(
    messages: List[Dict],
    config: dict,
    client_params: Optional[dict] = None,
) -> Tuple[List[str], List[dict]]:
    """并行调用参考模型，返回引用文本列表和健康的参考模型配置列表。

    包含去重、重试、降级策略。

    Args:
        messages: 截断后的消息列表
        config: 全局配置
        client_params: 客户端参数（temperature 等）

    Returns:
        (references, healthy_refs) 二元组
        references: 引用文本列表，格式为 "[ref_name] content" 或 "[ref_name] 调用失败: ..."
        healthy_refs: 健康的参考模型配置列表

    Raises:
        NoHealthyReferenceError: 所有参考模型均不健康
        AllReferencesFailedError: 所有参考模型均调用失败
    """
    client_params = client_params or {}
    moa_cfg = config.get("moa", {})

    ref_timeout = moa_cfg.get("reference_timeout", C.REFERENCE_MODEL_TIMEOUT)
    ref_temp = client_params.get("temperature", moa_cfg.get("reference_temperature", C.DEFAULT_REFERENCE_TEMPERATURE))
    ref_max_tokens = moa_cfg.get("reference_max_tokens", C.DEFAULT_REFERENCE_MAX_TOKENS)

    reference_models = config.get("reference_models") or []
    if not reference_models:
        raise NoHealthyReferenceError("未配置任何参考模型")

    # 过滤不健康参考模型
    healthy_refs: List[dict] = []
    for i, ref in enumerate(reference_models):
        ref_name = ref.get("name", f"ref-{i}")
        if is_model_healthy(ref_name):
            healthy_refs.append(ref)

    if not healthy_refs:
        raise NoHealthyReferenceError("所有参考模型均不健康（健康检查未通过）")

    # 并行调用参考模型（使用全局连接池）
    client = get_client(ref_timeout)
    tasks = [
        call_model(client, ref, messages, ref_temp, ref_max_tokens)
        for ref in healthy_refs
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # 对失败的参考模型重试
    retry_indices = [i for i, r in enumerate(results) if isinstance(r, Exception)]
    if retry_indices:
        logger.warning("参考模型重试: %d 个失败", len(retry_indices))
        retry_tasks = [
            call_model(client, healthy_refs[i], messages, ref_temp, ref_max_tokens)
            for i in retry_indices
        ]
        retry_results = await asyncio.gather(*retry_tasks, return_exceptions=True)
        for idx, retry_r in zip(retry_indices, retry_results):
            results[idx] = retry_r  # 重试结果替换

    # 过滤失败 + 构造引用文本
    references: List[str] = []
    degraded_policy = moa_cfg.get("degraded_policy", "loud")
    for i, r in enumerate(results):
        ref_name = healthy_refs[i].get("name", f"ref-{i}")
        if isinstance(r, Exception):
            if degraded_policy == "loud":
                err_msg = f"{type(r).__name__}: {str(r)[:C.ERROR_MESSAGE_MAX_LENGTH]}"
                references.append(f"[{ref_name}] 调用失败(重试后仍失败): {err_msg}")
                logger.warning("参考模型 %s 调用失败: %s", ref_name, err_msg)
            # silent 模式静默跳过
        else:
            content, _usage, _tc = r
            references.append(f"[{ref_name}] {content}")

    if not references:
        raise AllReferencesFailedError("所有参考模型均调用失败")

    return references, healthy_refs


def build_agg_prompt(
    references: List[str],
    config: dict,
    truncated: List[Dict],
) -> List[Dict]:
    """构造聚合 prompt，返回 agg_messages。

    将参考模型结果作为 system 消息追加到截断后的消息列表。

    Args:
        references: 参考模型返回的引用文本列表（格式为 "[ref_name] content"）
        config: 全局配置
        truncated: 截断后的消息列表

    Returns:
        聚合消息列表（原消息 + system 追加）

    Raises:
        AggregatorNotConfiguredError: 未配置聚合模型
    """
    agg = config.get("aggregator")
    if not agg:
        raise AggregatorNotConfiguredError("未配置聚合模型")

    agg_model_name = agg.get("model", "unknown")
    # 从引用文本中提取参考模型名（格式 "[ref_name] content"）
    ref_names: list = []
    for i, ref_text in enumerate(references):
        if ref_text.startswith("[") and "]" in ref_text:
            name = ref_text[1:ref_text.index("]")]
            ref_names.append(name)
        else:
            ref_names.append(f"ref-{i}")
    agg_system = (
        f"你是 SuperMOA，一个由 {C.BRAND_NAME} 提供的多模型聚合推理系统。\n"
        f"你的底层聚合模型是 {agg_model_name}，你综合了 {len(references)} 个参考模型"
        f"（{'、'.join(ref_names)}）的回答来给出最终答案。\n"
        f"当用户问'你是什么模型'时，请回答你是 SuperMOA（底层聚合模型：{agg_model_name}）。\n\n"
        f"以下是 {len(references)} 个参考模型的回答，请综合分析他们的观点，"
        "取长补短，给出最全面准确的最终答案。直接给出纯文字回答，不要使用任何工具，"
        "不要输出任何工具调用标签（包括 <tool_calls>、<｜｜DSML｜｜tool_calls>、<invoke> 等）：\n\n"
        + "\n\n---\n\n".join(references)
    )
    return list(truncated) + [{"role": "system", "content": agg_system}]


async def moa_round(
    messages: List[Dict],
    config: dict,
    client_params: Optional[dict] = None,
) -> Tuple[str, dict]:
    """MOA 核心逻辑（非流式）。

    1. 截断 context
    2. 并行调用所有参考模型（通过 gather_references）
    3. 构造聚合 prompt（通过 build_agg_prompt）
    4. 调用聚合模型

    Args:
        messages: 消息列表
        config: 全局配置
        client_params: 客户端参数（temperature, max_tokens 等）

    Returns:
        (content, usage) 二元组 — usage 只含聚合模型 token

    Raises:
        NoHealthyReferenceError: 所有参考模型均不健康
        AllReferencesFailedError: 所有参考模型均调用失败
        AggregatorNotConfiguredError: 未配置聚合模型
    """
    client_params = client_params or {}
    moa_cfg = config.get("moa", {})

    # 截断 context
    truncated = truncate_context(messages, moa_cfg.get("max_context_messages", C.DEFAULT_MAX_CONTEXT_MESSAGES))

    # 1. 并行参考请求（公共方法）
    references, healthy_refs = await gather_references(truncated, config, client_params)

    # 2. 构造聚合 prompt（公共方法）
    agg_messages = build_agg_prompt(references, config, truncated)

    # 3. 调用聚合模型
    agg = config["aggregator"]
    agg_timeout = moa_cfg.get("aggregator_timeout", C.AGGREGATOR_TIMEOUT)
    agg_temp = client_params.get("temperature", agg.get("temperature", C.DEFAULT_AGGREGATOR_TEMPERATURE))
    agg_max_tokens = client_params.get("max_tokens", agg.get("max_tokens", C.DEFAULT_AGGREGATOR_MAX_TOKENS))

    # 使用全局连接池调用聚合模型
    agg_client = get_client(agg_timeout)
    agg_content, agg_usage, _agg_tc = await call_model(
        agg_client, agg, agg_messages, agg_temp, agg_max_tokens
    )

    return agg_content, agg_usage or {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}


# ============================================================
# 透传
# ============================================================

async def passthrough(
    messages: List[Dict],
    model_cfg: dict,
    client_params: Optional[dict] = None,
) -> Tuple[str, dict, Optional[list]]:
    """透传给指定模型（非流式），传递所有客户端参数（含 tools 等）。

    Args:
        messages: 消息列表
        model_cfg: 模型配置 dict（含 base_url, api_key, model 等）
        client_params: 客户端参数（temperature, max_tokens, tools 等）

    Returns:
        (content, usage, tool_calls) 三元组
    """
    client_params = client_params or {}
    temp = client_params.get("temperature", C.DEFAULT_REFERENCE_TEMPERATURE)
    max_tokens = client_params.get("max_tokens", C.DEFAULT_AGGREGATOR_MAX_TOKENS)
    extra = {k: v for k, v in client_params.items() if k not in ("temperature", "max_tokens")}

    # 使用全局连接池
    client = get_client(C.DEFAULT_HTTP_TIMEOUT)
    return await call_model(client, model_cfg, messages, temp, max_tokens, extra)


# ============================================================
# 公共工具方法
# ============================================================

async def call_model(
    client: httpx.AsyncClient,
    model_cfg: dict,
    messages: List[Dict],
    temperature: float,
    max_tokens: int,
    extra_params: Optional[dict] = None,
) -> Tuple[str, dict, Optional[list]]:
    """调用单个 OpenAI 兼容模型，返回 (content_str, usage_dict, tool_calls)。

    使用 .get() 安全取值，避免 KeyError。

    Args:
        client: httpx 异步客户端
        model_cfg: 模型配置 dict（含 model, base_url, api_key）
        messages: 消息列表
        temperature: 温度参数
        max_tokens: 最大 token 数
        extra_params: 额外参数（tools, tool_choice 等）

    Returns:
        (content, usage, tool_calls) 三元组

    Raises:
        UpstreamError: 上游调用失败（HTTP 错误或响应解析失败）
    """
    model_name = model_cfg.get("model", "")
    base_url = model_cfg.get("base_url", "")
    api_key = model_cfg.get("api_key", "")

    payload = {
        "model": model_name,
        "messages": messages,
        "temperature": temperature,
        "stream": False,
        "max_tokens": max_tokens,
    }
    # 传递额外参数（tools, tool_choice 等）
    if extra_params:
        for k, v in extra_params.items():
            if k not in payload and v is not None:
                payload[k] = v

    try:
        resp = await client.post(
            f"{base_url.rstrip('/')}/chat/completions",
            json=payload,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
        )
        resp.raise_for_status()
    except httpx.HTTPStatusError as e:
        err_body = ""
        try:
            err_body = e.response.text[:C.ERROR_MESSAGE_MAX_LENGTH]
        except (AttributeError, UnicodeDecodeError) as e2:
            logger.debug("错误响应体读取失败: %s", str(e2)[:100])
        logger.error("上游 HTTP 错误: model=%s status=%s body=%s", model_name, e.response.status_code, err_body)
        friendly_msg = friendly_error_message(err_body, e.response.status_code)
        raise UpstreamError(friendly_msg) from e
    except httpx.RequestError as e:
        logger.error("上游请求失败: model=%s error=%s", model_name, str(e)[:C.ERROR_MESSAGE_MAX_LENGTH])
        friendly_msg = friendly_error_message(f"{type(e).__name__}: {str(e)[:C.ERROR_MESSAGE_MAX_LENGTH]}")
        raise UpstreamError(friendly_msg) from e

    try:
        data = resp.json()
        msg = data["choices"][0]["message"]
        content = msg.get("content", "")
        tool_calls = msg.get("tool_calls")
        usage = data.get("usage") or {}
        return content, usage, tool_calls
    except (KeyError, IndexError, ValueError) as e:
        logger.error("上游响应解析失败: model=%s error=%s", model_name, str(e))
        raise UpstreamError(f"响应解析失败: {type(e).__name__}: {str(e)[:C.ERROR_MESSAGE_MAX_LENGTH]}") from e


def truncate_context(messages: List[Dict], max_messages: Optional[int]) -> List[Dict]:
    """保留所有 system 消息 + 最后 N 条非 system 消息。

    Args:
        messages: 原始消息列表
        max_messages: 保留的最大非 system 消息数（None 或 <=0 表示不截断）

    Returns:
        截断后的消息列表
    """
    if not max_messages or max_messages <= 0 or len(messages) <= max_messages:
        return messages
    system_msgs = [m for m in messages if m.get("role") == "system"]
    non_system = [m for m in messages if m.get("role") != "system"]
    truncated_non_system = non_system[-max_messages:]
    return system_msgs + truncated_non_system
