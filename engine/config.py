"""SuperMOA — 配置加载/保存/校验"""
import copy
from pathlib import Path
from typing import Optional

import yaml

from engine.vendors import get_default_config_template, find_vendor
from engine import constants as C
from engine.exceptions import ConfigError, log_and_raise

CONFIG_DIR = Path.home() / ".moa-gateway"
CONFIG_FILE = CONFIG_DIR / "config.yaml"
INITIALIZED_FILE = CONFIG_DIR / ".initialized"


def is_first_run() -> bool:
    return not CONFIG_FILE.exists()


def ensure_config() -> bool:
    """首次启动时生成默认配置。返回 True 表示刚创建（首次运行）"""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    if not CONFIG_FILE.exists():
        template = get_default_config_template()
        save_config(template)
        return True
    return False


def load_config() -> dict:
    """加载配置。文件不存在时返回默认模板"""
    if not CONFIG_FILE.exists():
        return get_default_config_template()
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    # 合并默认值（防止字段缺失）
    return _merge_defaults(data)


def save_config(config: dict):
    """保存配置到 yaml"""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        yaml.safe_dump(config, f, allow_unicode=True, sort_keys=False)


def get_config_path() -> Path:
    return CONFIG_FILE


def is_first_run() -> bool:
    """是否首次运行（.initialized 标记文件不存在）"""
    return not INITIALIZED_FILE.exists()


def mark_initialized():
    """标记已完成首启引导"""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    INITIALIZED_FILE.write_text("1", encoding="utf-8")


def validate_config(config: dict) -> list:
    """校验配置，返回错误信息列表（空表示通过）"""
    errors = []

    # gateway
    gw = config.get("gateway") or {}
    if not gw.get("host"):
        errors.append("gateway.host 不能为空")
    port = gw.get("port")
    if not isinstance(port, int) or not (C.MIN_PORT <= port <= C.MAX_PORT):
        errors.append(f"gateway.port 必须是 {C.MIN_PORT}-{C.MAX_PORT} 的整数")

    # reference_models
    refs = config.get("reference_models") or []
    if not isinstance(refs, list):
        errors.append("reference_models 必须是列表")
    else:
        if len(refs) < C.MIN_REFERENCE_MODELS:
            errors.append(f"至少需要 {C.MIN_REFERENCE_MODELS} 个参考模型")
        if len(refs) > C.MAX_REFERENCE_MODELS:
            errors.append(f"参考模型最多 {C.MAX_REFERENCE_MODELS} 个")
        for i, r in enumerate(refs):
            err_prefix = f"reference_models[{i}]"
            if not r.get("base_url"):
                errors.append(f"{err_prefix}.base_url 不能为空")
            if not r.get("api_key"):
                errors.append(f"{err_prefix}.api_key 不能为空")
            if not r.get("model"):
                errors.append(f"{err_prefix}.model 不能为空")
            if not r.get("trigger"):
                errors.append(f"{err_prefix}.trigger 不能为空（触发词，如 hy3：）")

    # aggregator
    agg = config.get("aggregator")
    if not agg:
        errors.append("aggregator 不能为空")
    else:
        if not agg.get("trigger"):
            errors.append("aggregator.trigger 不能为空（触发词，如 hh：）")
        if not agg.get("base_url"):
            errors.append("aggregator.base_url 不能为空")
        if not agg.get("api_key"):
            errors.append("aggregator.api_key 不能为空")
        if not agg.get("model"):
            errors.append("aggregator.model 不能为空")

    # default_passthrough（可选）
    dp = config.get("default_passthrough")
    if dp:
        if not dp.get("base_url"):
            errors.append("default_passthrough.base_url 不能为空")
        if not dp.get("api_key"):
            errors.append("default_passthrough.api_key 不能为空")
        if not dp.get("model"):
            errors.append("default_passthrough.model 不能为空")

    return errors


def fill_vendor_info(vendor_name: str, custom_model: Optional[str] = None) -> dict:
    """根据厂商名填入 base_url，返回部分配置片段"""
    v = find_vendor(vendor_name)
    if not v:
        return {}
    return {
        "provider": v["protocol"],
        "base_url": v["base_url"],
        "model": custom_model or (v["models"][0] if v["models"] else ""),
    }


def normalize_config(config: dict) -> dict:
    """规范化配置：name 为空时自动用 model 填充，避免健康检查/聚合标识冲突"""
    import copy
    result = copy.deepcopy(config)
    used_names = set()

    def _fill_name(item):
        name = (item.get("name") or "").strip()
        if not name:
            base = item.get("model", "model")
            name = base
            # 防重名
            n = 2
            while name in used_names:
                name = f"{base}-{n}"
                n += 1
        used_names.add(name)
        item["name"] = name

    for ref in result.get("reference_models") or []:
        _fill_name(ref)
        # trigger 默认值：model 名 + ：
        if not ref.get("trigger"):
            ref["trigger"] = ref.get("model", "") + C.DEFAULT_TRIGGER_SUFFIX
    if result.get("aggregator"):
        _fill_name(result["aggregator"])
        if not result["aggregator"].get("trigger"):
            result["aggregator"]["trigger"] = C.DEFAULT_AGGREGATOR_TRIGGER
    if result.get("default_passthrough"):
        _fill_name(result["default_passthrough"])
    return result


def _merge_defaults(data: dict) -> dict:
    """合并默认值，防止老配置缺字段"""
    template = get_default_config_template()
    result = copy.deepcopy(template)
    for k, v in data.items():
        if isinstance(v, dict) and isinstance(result.get(k), dict):
            result[k].update(v)
        else:
            result[k] = v
    # 保证 moa 内层字段也有默认值
    moa_default = get_default_config_template()["moa"]
    if "moa" not in result or not isinstance(result["moa"], dict):
        result["moa"] = {}
    for k, v in moa_default.items():
        result["moa"].setdefault(k, v)
    return result
