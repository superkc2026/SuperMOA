"""SuperMOA — 厂商预置列表（含价格/优势/推荐组合）

价格单位：元/百万 token（人民币），参考价格（2026-07），以厂商官网为准。
"""

VENDORS = [
    {
        "name": "DeepSeek",
        "base_url": "https://api.deepseek.com/v1",
        "protocol": "openai",
        "models": ["deepseek-v4-flash", "deepseek-v4-pro"],
        "model_info": {
            "deepseek-v4-flash": {"price_input": 1, "price_output": 2, "desc": "快速版，日常对话/代码补全"},
            "deepseek-v4-pro": {"price_input": 4, "price_output": 16, "desc": "旗舰版，复杂推理/长文"},
        },
        "strengths": "代码/数学/推理强，性价比标杆，国内首选",
    },
    {
        "name": "阿里通义千问",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "protocol": "openai",
        "models": ["qwen3.5-flash", "qwen3-plus"],
        "model_info": {
            "qwen3.5-flash": {"price_input": 0.5, "price_output": 2, "desc": "极速版，便宜量大"},
            "qwen3-plus": {"price_input": 4, "price_output": 12, "desc": "增强版，中文理解强"},
        },
        "strengths": "中文理解/长文档/工具调用强，阿里云生态",
    },
    {
        "name": "腾讯混元",
        "base_url": "https://tokenhub.tencentmaas.com/v1",
        "protocol": "openai",
        "models": ["hy3", "hunyuan-turbo"],
        "model_info": {
            "hy3": {"price_input": 2, "price_output": 5, "desc": "标准版，均衡"},
            "hunyuan-turbo": {"price_input": 15, "price_output": 40, "desc": "旗舰版，推理强"},
        },
        "strengths": "中文创作/多模态/腾讯生态整合",
    },
    {
        "name": "智谱 GLM",
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "protocol": "openai",
        "models": ["glm-5-plus", "glm-5-flash"],
        "model_info": {
            "glm-5-plus": {"price_input": 5, "price_output": 15, "desc": "旗舰版，综合能力强"},
            "glm-5-flash": {"price_input": 1, "price_output": 2, "desc": "快速版，性价比高"},
        },
        "strengths": "中英双语/代码/Agent 能力强，清华系",
    },
    {
        "name": "MiniMax",
        "base_url": "https://api.minimaxi.com/v1",
        "protocol": "openai",
        "models": ["MiniMax-M3", "MiniMax-T1"],
        "model_info": {
            "MiniMax-M3": {"price_input": 1, "price_output": 3, "desc": "通用版，对话流畅"},
            "MiniMax-T1": {"price_input": 3, "price_output": 8, "desc": "推理版，逻辑强"},
        },
        "strengths": "长上下文/角色扮演/语音对话强",
    },
    {
        "name": "小米 MiMo",
        "base_url": "https://api.xiaomimimo.com/v1",
        "protocol": "openai",
        "models": ["mimo-v2.5-pro-ultraspeed"],
        "model_info": {
            "mimo-v2.5-pro-ultraspeed": {"price_input": 0.5, "price_output": 1, "desc": "超低延迟，极便宜"},
        },
        "strengths": "极速响应/成本极低，适合高并发",
    },
    {
        "name": "百度千帆",
        "base_url": "https://aip.baidubce.com/rpc/2.0/ai_custom/v1/wenxinworkshop/chat",
        "protocol": "openai",
        "models": ["ernie-4.5-turbo"],
        "model_info": {
            "ernie-4.5-turbo": {"price_input": 8, "price_output": 24, "desc": "文心4.5，中文强"},
        },
        "strengths": "中文理解/知识图谱/百度搜索整合",
    },
    {
        "name": "字节豆包",
        "base_url": "https://ark.cn-beijing.volces.com/api/v3",
        "protocol": "openai",
        "models": ["doubao-pro-32k"],
        "model_info": {
            "doubao-pro-32k": {"price_input": 0.8, "price_output": 2, "desc": "便宜量大，32k 上下文"},
        },
        "strengths": "便宜/长上下文/字节生态",
    },
    {
        "name": "Moonshot",
        "base_url": "https://api.moonshot.cn/v1",
        "protocol": "openai",
        "models": ["moonshot-v1-8k"],
        "model_info": {
            "moonshot-v1-8k": {"price_input": 12, "price_output": 12, "desc": "Kimi 同源，长文本强"},
        },
        "strengths": "超长上下文/文档解析强，Kimi 同源",
    },
    {
        "name": "零一万物",
        "base_url": "https://api.lingyiwanwu.com/v1",
        "protocol": "openai",
        "models": ["yi-lightning"],
        "model_info": {
            "yi-lightning": {"price_input": 0.99, "price_output": 0.99, "desc": "极速版，输入输出同价"},
        },
        "strengths": "中英双语/性价比高，李开复团队",
    },
]


# 推荐组合（国内为主）
RECOMMENDED_COMBOS = [
    {
        "name": "性价比组合（推荐）",
        "desc": "日常使用最划算，质量够用，单次 MOA 成本约 ¥0.02",
        "references": [
            {"vendor": "DeepSeek", "model": "deepseek-v4-flash", "reason": "代码/推理强"},
            {"vendor": "阿里通义千问", "model": "qwen3.5-flash", "reason": "中文理解强"},
            {"vendor": "智谱 GLM", "model": "glm-5-flash", "reason": "中英双语均衡"},
        ],
        "aggregator": {"vendor": "DeepSeek", "model": "deepseek-v4-pro", "reason": "综合能力标杆"},
        "passthrough": {"vendor": "DeepSeek", "model": "deepseek-v4-flash", "reason": "日常快省钱"},
    },
    {
        "name": "质量优先组合",
        "desc": "复杂任务用，质量最高，单次 MOA 成本约 ¥0.08",
        "references": [
            {"vendor": "阿里通义千问", "model": "qwen3-plus", "reason": "中文深度"},
            {"vendor": "智谱 GLM", "model": "glm-5-plus", "reason": "综合能力强"},
            {"vendor": "腾讯混元", "model": "hunyuan-turbo", "reason": "推理强"},
        ],
        "aggregator": {"vendor": "DeepSeek", "model": "deepseek-v4-pro", "reason": "综合最强"},
        "passthrough": {"vendor": "智谱 GLM", "model": "glm-5-flash", "reason": "日常够用"},
    },
    {
        "name": "极致省钱组合",
        "desc": "预算紧张用，单次 MOA 成本约 ¥0.01",
        "references": [
            {"vendor": "字节豆包", "model": "doubao-pro-32k", "reason": "便宜量大"},
            {"vendor": "阿里通义千问", "model": "qwen3.5-flash", "reason": "极速便宜"},
            {"vendor": "零一万物", "model": "yi-lightning", "reason": "输入输出同价"},
        ],
        "aggregator": {"vendor": "阿里通义千问", "model": "qwen3.5-flash", "reason": "省钱聚合"},
        "passthrough": {"vendor": "字节豆包", "model": "doubao-pro-32k", "reason": "最便宜"},
    },
]


def list_vendor_names() -> list:
    return [v["name"] for v in VENDORS]


def find_vendor(name: str):
    for v in VENDORS:
        if v["name"] == name:
            return v
    return None


def get_default_config_template() -> dict:
    """返回默认配置模板（首次启动用）"""
    return {
        "gateway": {"host": "127.0.0.1", "port": 12345},
        "reference_models": [],
        "aggregator": None,
        "default_passthrough": None,
        "moa": {
            "reference_temperature": 0.7,
            "reference_max_tokens": 2048,
            "reference_timeout": 30,
            "aggregator_timeout": 120,
            "degraded_policy": "loud",
            "stream": True,
            "max_context_messages": 10,
        },
    }
