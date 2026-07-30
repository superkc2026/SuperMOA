"""SuperMOA — 管理端点（config/test/demo/vendors/logs/health/usage）"""
import asyncio
import logging

from fastapi import APIRouter
from fastapi.responses import FileResponse, JSONResponse, Response
import httpx

from engine.auth import (
    verify_api_key, ensure_api_key, regenerate_api_key,
    get_current_key, mask_key,
)
from engine.config import (
    load_config, save_config, validate_config, get_config_path,
    normalize_config, _merge_defaults, is_first_run, mark_initialized,
)
from engine.vendors import VENDORS, RECOMMENDED_COMBOS
from engine import health as health_module
from engine import constants as C
from engine.exceptions import friendly_error_message
from engine.log_manager import get_log_manager

logger = logging.getLogger("supermoa")

router = APIRouter()

# 静态文件路径
from app import WEB_DIR  # noqa: E402

# Web 配置页静态端点已在 app.py 定义（/, /app.js），这里不重复

# ============================================================
# 健康检查端点
# ============================================================
@router.get("/health")
async def health():
    return {"status": "ok", "version": "1.0.0"}


@router.get("/api/health-status")
async def api_health_status():
    """返回各模型健康状态"""
    return {"models": health_module.get_health_status()}


@router.post("/api/health-check")
async def api_trigger_health_check():
    """手动触发一次健康检查（同步等待结果）"""
    config = load_config()
    await health_module._check_all_models(config)
    return {"status": "ok", "models": health_module.get_health_status()}


# ============================================================
# 模型列表端点
# ============================================================
@router.get("/v1/models")
async def list_models():
    """OpenAI 兼容的 /v1/models 端点"""
    import time
    config = load_config()
    models = []
    seen = set()

    def _add(model_id, owned_by):
        if model_id and model_id not in seen:
            models.append({
                "id": model_id, "object": "model",
                "created": int(time.time()), "owned_by": owned_by,
            })
            seen.add(model_id)

    _add("SuperMOA", "supermoa")
    for ref in (config.get("reference_models") or []):
        _add(ref.get("model", ""), ref.get("name") or "supermoa")
    agg = config.get("aggregator")
    if agg:
        _add(agg.get("model", ""), agg.get("name") or "supermoa")
    pass_cfg = config.get("default_passthrough")
    if pass_cfg:
        _add(pass_cfg.get("model", ""), pass_cfg.get("name") or "supermoa")

    return {"object": "list", "data": models}


# ============================================================
# 日志端点
# ============================================================
@router.get("/api/logs")
async def api_logs():
    """返回最近 100 条请求路由日志"""
    return {"logs": get_log_manager().get_logs()}


@router.get("/api/logs/export")
async def api_logs_export(format: str = "md"):
    """导出调用记录：format=xlsx 或 md"""
    logs = list(get_log_manager().get_logs())
    if format == "xlsx":
        try:
            from openpyxl import Workbook
            from io import BytesIO
            wb = Workbook()
            ws = wb.active
            ws.title = "调用记录"
            ws.append(["时间", "来源", "路由", "实际模型", "触发词", "消息预览"])
            for l in logs:
                ws.append([l.get("time", ""), l.get("client", ""), l.get("route", ""),
                           l.get("actual_model", ""), l.get("prefix", "无前缀"), l.get("prompt_preview", "")])
            buf = BytesIO()
            wb.save(buf)
            return Response(content=buf.getvalue(), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            headers={"Content-Disposition": "attachment; filename=moa-logs.xlsx"})
        except Exception as e:
            return JSONResponse({"error": {"message": f"Excel 导出失败: {e}"}}, status_code=500)
    else:
        lines = ["| 时间 | 来源 | 路由 | 实际模型 | 触发词 | 消息预览 |", "|------|------|------|---------|--------|---------|"]
        for l in logs:
            lines.append(f"| {l.get('time','')} | {l.get('client','')} | {l.get('route','')} | {l.get('actual_model','')} | {l.get('prefix','无前缀')} | {l.get('prompt_preview','')} |")
        content = "\n".join(lines)
        return Response(content=content, media_type="text/markdown",
                        headers={"Content-Disposition": "attachment; filename=moa-logs.md"})


# ============================================================
# 配置端点
# ============================================================
@router.get("/api/vendors")
async def api_vendors():
    return {"vendors": VENDORS}


@router.get("/api/config")
async def api_get_config():
    """返回当前配置（mask api_key）"""
    from app import _mask_config
    config = load_config()
    return _mask_config(config)


@router.post("/api/config")
async def api_save_config(body: dict):
    """保存配置"""
    from app import _mask_config, _unmask_config
    current = load_config()
    new_config = _unmask_config(body, current)

    errors = validate_config(new_config)
    if errors:
        return JSONResponse(
            {"error": {"message": "配置校验失败", "details": errors, "type": "validation_error", "code": 400}},
            status_code=400,
        )

    new_config = normalize_config(new_config)
    save_config(new_config)
    mark_initialized()
    try:
        health_module.clear_health_status()
    except Exception as e:
        logger.warning("健康状态清空失败: %s", str(e)[:100])
    return {"status": "ok", "message": "配置已保存"}


@router.get("/api/config/export")
async def api_export_config():
    """导出配置文件（api_key 已脱敏）"""
    from app import _mask_config
    import yaml as _yaml
    config = load_config()
    masked = _mask_config(config)
    content = _yaml.dump(masked, allow_unicode=True, sort_keys=False, default_flow_style=False)
    return Response(
        content=content,
        media_type="application/x-yaml",
        headers={"Content-Disposition": "attachment; filename=config.yaml"},
    )


@router.post("/api/config/import")
async def api_import_config(body: dict):
    """导入配置"""
    import yaml
    yaml_text = body.get("yaml", "")
    if not yaml_text:
        return JSONResponse(
            {"error": {"message": "yaml 内容为空", "type": "invalid_request", "code": 400}},
            status_code=400,
        )
    try:
        data = yaml.safe_load(yaml_text) or {}
    except yaml.YAMLError as e:
        return JSONResponse(
            {"error": {"message": f"YAML 解析失败: {str(e)[:200]}", "type": "parse_error", "code": 400}},
            status_code=400,
        )

    merged = _merge_defaults(data)
    merged = normalize_config(merged)

    errors = validate_config(merged)
    if errors:
        return JSONResponse(
            {"error": {"message": "导入配置校验失败", "details": errors, "type": "validation_error", "code": 400}},
            status_code=400,
        )

    save_config(merged)
    try:
        health_module.clear_health_status()
    except Exception as e:
        logger.warning("健康状态清空失败: %s", str(e)[:100])
    return {"status": "ok", "message": "配置已导入"}


# ============================================================
# 测试端点
# ============================================================
@router.post("/api/test-all")
async def api_test_all():
    """批量测试当前配置的所有模型连通性"""
    config = load_config()
    models = []
    for ref in (config.get("reference_models") or []):
        models.append({"name": ref.get("name") or ref.get("model", ""), "base_url": ref.get("base_url", ""), "api_key": ref.get("api_key", ""), "model": ref.get("model", "")})
    agg = config.get("aggregator")
    if agg:
        models.append({"name": agg.get("name") or agg.get("model", ""), "base_url": agg.get("base_url", ""), "api_key": agg.get("api_key", ""), "model": agg.get("model", "")})
    pass_cfg = config.get("default_passthrough")
    if pass_cfg:
        models.append({"name": pass_cfg.get("name") or pass_cfg.get("model", ""), "base_url": pass_cfg.get("base_url", ""), "api_key": pass_cfg.get("api_key", ""), "model": pass_cfg.get("model", "")})
    if not models:
        return {"results": []}

    async def _test_one(m):
        base_url = (m.get("base_url") or "").rstrip("/")
        api_key = m.get("api_key") or ""
        model = m.get("model") or ""
        name = m.get("name") or model
        if not (base_url and api_key and model):
            return {"name": name, "status": "error", "code": 0, "message": "配置不完整"}
        try:
            async with httpx.AsyncClient(timeout=C.TEST_CONNECTION_TIMEOUT) as client:
                resp = await client.post(
                    f"{base_url}/chat/completions",
                    json={"model": model, "messages": [{"role": "user", "content": "ping"}], "max_tokens": 5, "temperature": 0},
                    headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                )
            if resp.status_code == 200:
                return {"name": name, "status": "ok", "code": 200}
            return {"name": name, "status": "error", "code": resp.status_code, "message": resp.text[:200]}
        except httpx.TimeoutException:
            return {"name": name, "status": "error", "code": 0, "message": f"连接超时（{C.TEST_CONNECTION_TIMEOUT}s），请检查网络"}
        except Exception as e:
            friendly_msg = friendly_error_message(f"{type(e).__name__}: {str(e)[:150]}")
            return {"name": name, "status": "error", "code": 0, "message": friendly_msg}

    tasks = [_test_one(m) for m in models]
    results = await asyncio.gather(*tasks)
    return {"results": list(results)}


@router.post("/api/test")
async def api_test_connection(body: dict):
    """测试某个模型配置能否调通"""
    from app import _mask_config
    base_url = body.get("base_url", "").rstrip("/")
    api_key = body.get("api_key", "")
    model = body.get("model", "")
    if "..." in api_key:
        config = load_config()
        candidates = list(config.get("reference_models") or [])
        if config.get("aggregator"):
            candidates.append(config["aggregator"])
        if config.get("default_passthrough"):
            candidates.append(config["default_passthrough"])
        for c in candidates:
            if c.get("base_url", "").rstrip("/") == base_url and c.get("model") == model:
                api_key = c.get("api_key", "")
                break
    if not (base_url and api_key and model):
        return JSONResponse(
            {"status": "error", "code": 0, "message": "base_url / api_key / model 不能为空（api_key 可能是 mask 格式且未找到匹配配置，请先保存配置）"},
            status_code=400,
        )
    try:
        async with httpx.AsyncClient(timeout=C.TEST_CONNECTION_TIMEOUT) as client:
            resp = await client.post(
                f"{base_url}/chat/completions",
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": "ping"}],
                    "max_tokens": 5,
                    "temperature": 0,
                },
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
            )
        if resp.status_code == 200:
            try:
                data = resp.json()
                content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                return {"status": "ok", "code": 200, "preview": content[:100]}
            except (KeyError, IndexError, ValueError) as e:
                logger.warning("测试连接响应解析失败: %s", str(e)[:100])
                return {"status": "ok", "code": 200, "preview": "(响应已收到但无法解析)"}
        return {
            "status": "error",
            "code": resp.status_code,
            "message": friendly_error_message(resp.text[:500], resp.status_code),
        }
    except httpx.TimeoutException:
        return {"status": "error", "code": 0, "message": f"连接超时（{C.TEST_CONNECTION_TIMEOUT}s），请检查网络"}
    except Exception as e:
        friendly_msg = friendly_error_message(f"{type(e).__name__}: {str(e)[:300]}")
        return {"status": "error", "code": 0, "message": friendly_msg}


# ============================================================
# 演示端点
# ============================================================
@router.post("/api/demo")
async def api_demo(body: dict = None):
    """MOA 演示"""
    try:
        from engine.orchestrator import call_model
        from engine.http_client import get_client
        config = load_config()
        refs = config.get("reference_models") or []
        agg = config.get("aggregator")
        if not refs or not agg:
            return JSONResponse({"error": {"message": "未配置参考模型或聚合模型", "type": "config_error", "code": 400}}, status_code=400)
        prompt = (body or {}).get("prompt", "用一句话解释什么是量子计算，让小学生都能懂")
        messages = [{"role": "user", "content": prompt}]
        moa_cfg = config.get("moa", {})
        ref_temp = moa_cfg.get("reference_temperature", C.DEFAULT_REFERENCE_TEMPERATURE)
        ref_max = moa_cfg.get("reference_max_tokens", C.DEFAULT_REFERENCE_MAX_TOKENS)
        ref_timeout = moa_cfg.get("reference_timeout", C.REFERENCE_MODEL_TIMEOUT)
        client = get_client(ref_timeout)
        tasks = [call_model(client, ref, messages, ref_temp, min(ref_max, 300)) for ref in refs]
        ref_results = await asyncio.gather(*tasks, return_exceptions=True)
        ref_outputs = []
        for i, r in enumerate(ref_results):
            name = refs[i].get("name", f"ref-{i}")
            if isinstance(r, Exception):
                ref_outputs.append({"name": name, "model": refs[i].get("model", ""), "content": f"[调用失败] {type(r).__name__}: {str(r)[:100]}", "error": True})
            else:
                content, _, _ = r
                ref_outputs.append({"name": name, "model": refs[i].get("model", ""), "content": content, "error": False})
        ref_texts = []
        for r in ref_outputs:
            if not r.get("error"):
                ref_texts.append(f"[{r['name']}({r['model']})] {r['content']}")
        ref_block = "\n\n---\n\n".join(ref_texts) if ref_texts else "(无可用参考)"
        agg_system = "你是最优秀的综合分析者。以下是多个参考模型的回答。请综合他们的观点给出最终答案。\n要求：在答案末尾，用【引用分析】段落明确标注你参考了哪些模型的哪些观点。\n\n参考模型回答：\n\n" + ref_block
        agg_messages = messages + [{"role": "system", "content": agg_system}]
        agg_temp = agg.get("temperature", C.DEFAULT_AGGREGATOR_TEMPERATURE)
        agg_max = agg.get("max_tokens", C.DEFAULT_AGGREGATOR_MAX_TOKENS)
        try:
            agg_client = get_client(moa_cfg.get("aggregator_timeout", C.AGGREGATOR_TIMEOUT))
            agg_content, _, _ = await call_model(agg_client, agg, agg_messages, agg_temp, min(agg_max, 800))
            agg_output = {"content": agg_content, "error": False}
        except Exception as e:
            agg_output = {"content": f"[聚合失败] {type(e).__name__}: {str(e)[:200]}", "error": True}
        return {"prompt": prompt, "references": ref_outputs, "aggregator": {"name": agg.get("name", ""), "model": agg.get("model", ""), **agg_output}}
    except Exception as e:
        return JSONResponse({"error": {"message": f"演示失败: {type(e).__name__}: {str(e)[:300]}", "type": "internal_error", "code": 500}}, status_code=500)


# ============================================================
# 推荐组合
# ============================================================
@router.get("/api/recommended-combos")
async def api_recommended_combos():
    return {"combos": RECOMMENDED_COMBOS}


# ============================================================
# API Key 端点
# ============================================================
@router.get("/api/key")
async def api_get_key():
    """获取当前 API Key（明文，仅本地访问）"""
    key = get_current_key()
    return {"key": key, "masked": mask_key(key)}


@router.post("/api/regenerate-key")
async def api_regenerate_key():
    new_key = regenerate_api_key()
    return {"key": new_key, "masked": mask_key(new_key)}


# ============================================================
# 服务状态
# ============================================================
@router.get("/api/status")
async def api_status():
    """服务状态"""
    config = load_config()
    return {
        "config_path": str(get_config_path()),
        "is_first_run": is_first_run(),
        "reference_models_count": len(config.get("reference_models") or []),
        "aggregator_configured": bool(config.get("aggregator")),
        "passthrough_configured": bool(config.get("default_passthrough")),
        "masked_key": mask_key(get_current_key()),
    }


# ============================================================
# 用量统计端点 (REQ-13)
# ============================================================
@router.get("/api/usage")
async def api_usage(days: int = 7):
    """返回近 N 天的用量统计汇总"""
    from engine.usage import get_usage_summary, get_usage_total
    summary = get_usage_summary(days)
    total = get_usage_total(days)
    return {
        "days": days,
        "summary": summary,
        "total": total,
    }


@router.get("/api/usage/export")
async def export_usage():
    """导出用量统计为 CSV"""
    import csv
    import io
    from engine.usage import get_usage_summary
    data = get_usage_summary(7)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["date", "model", "route", "prompt_tokens", "completion_tokens", "total_tokens", "cost", "count"])
    for row in data:
        writer.writerow([
            row.get("date", ""),
            row.get("model", ""),
            row.get("route", ""),
            row.get("prompt_tokens", 0),
            row.get("completion_tokens", 0),
            row.get("total_tokens", 0),
            row.get("cost", 0.0),
            row.get("count", 0),
        ])
    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=usage.csv"},
    )


# ============================================================
# 版本更新检查端点 (T05)
# ============================================================
@router.get("/api/check-update")
async def check_update():
    """检查是否有新版本可用"""
    from engine.updater import check_for_update
    return check_for_update()


# ============================================================
# 错误上报开关端点 (T05)
# ============================================================
@router.post("/api/error-reporting/toggle")
async def toggle_error_reporting(body: dict = None):
    """开启/关闭错误上报（opt-in）"""
    from engine import error_reporter
    enabled = (body or {}).get("enabled", False)
    config = load_config()
    config.setdefault("error_reporting", {})["enabled"] = enabled
    save_config(config)
    if enabled:
        error_reporter.install()
    else:
        error_reporter.uninstall()
    return {"enabled": enabled}


# ============================================================
# Profile 管理端点 (REQ-20)
# ============================================================
@router.get("/api/profiles")
async def api_list_profiles():
    """列出所有配置 Profile"""
    from engine.profiles import list_profiles
    return {"profiles": list_profiles()}


@router.post("/api/profiles/switch")
async def api_switch_profile(body: dict):
    """切换到指定 Profile"""
    from engine.profiles import switch_profile
    name = (body or {}).get("name", "")
    if not name:
        return JSONResponse(
            {"error": {"message": "name 不能为空", "type": "invalid_request", "code": 400}},
            status_code=400,
        )
    ok = switch_profile(name)
    if not ok:
        return JSONResponse(
            {"error": {"message": f"Profile '{name}' 不存在", "type": "not_found", "code": 404}},
            status_code=404,
        )
    # 切换后清空健康状态
    try:
        health_module.clear_health_status()
    except Exception as e:
        logger.warning("健康状态清空失败: %s", str(e)[:100])
    return {"status": "ok", "active_profile": name}


@router.post("/api/profiles")
async def api_save_profile(body: dict):
    """将当前配置保存为新 Profile"""
    from engine.profiles import save_current_as_profile
    name = (body or {}).get("name", "")
    if not name:
        return JSONResponse(
            {"error": {"message": "name 不能为空", "type": "invalid_request", "code": 400}},
            status_code=400,
        )
    save_current_as_profile(name)
    return {"status": "ok", "message": f"已保存为 Profile '{name}'"}


@router.delete("/api/profiles/{name}")
async def api_delete_profile(name: str):
    """删除指定 Profile"""
    from engine.profiles import delete_profile, get_active_profile
    if name == get_active_profile():
        return JSONResponse(
            {"error": {"message": "不能删除当前激活的 Profile", "type": "conflict", "code": 409}},
            status_code=409,
        )
    ok = delete_profile(name)
    if not ok:
        return JSONResponse(
            {"error": {"message": f"Profile '{name}' 不存在", "type": "not_found", "code": 404}},
            status_code=404,
        )
    return {"status": "ok", "message": f"已删除 Profile '{name}'"}
