# SuperMOA 修复方案 + 任务分解

## 1. 实现策略

分 **3 批次**，按依赖链推进：

| 批次 | 目标 | 涉及任务 |
|------|------|----------|
| **批次 1** | P0 Bug 修复 + 品牌统一 + 核心引擎重构 | T01, T02 |
| **批次 2** | 架构拆分 + 安全加固 + 用量统计 | T03, T04 |
| **批次 3** | 推广合规 + 签名 + 版本更新 | T05 |

**依赖链**：T01 → T02 → T03 → {T04, T05}

---

## 2. 关键技术方案

### REQ-06 流式/非流式合并

抽 2 个公共方法到 `orchestrator.py`：

```python
async def _gather_references(messages, config, client_params) -> list[str]:
    """并行调用参考模型，返回引用文本列表（含去重、重试、降级）"""

def _build_agg_prompt(references, config, truncated) -> list[dict]:
    """构造聚合 prompt，返回 agg_messages"""
```

- `moa_round()`：调 `_gather_references` → `_build_agg_prompt` → `_call_model`（非流式）
- `moa_round_stream()`：调同样两步 → 上游 `client.stream()` 转发 SSE
- 消除 `streaming.py` 中重复的参考模型调度+聚合 prompt 构造（约 80 行）

### REQ-12 main.py 拆分

| 新模块 | 职责 | 行数 |
|--------|------|------|
| `app.py` | FastAPI 创建 + startup/shutdown + run_server | ~80 |
| `routes/chat.py` | `/v1/chat/completions` 端点 + 路由执行 | ~120 |
| `routes/admin.py` | config/test/demo/vendors/logs/health 端点 | ~200 |
| `engine/log_manager.py` | 日志记录/去重/轮转/加载 | ~100 |
| `engine/usage.py` | 用量统计存储+查询 | ~80 |
| `main.py` | 仅 CLI 入口 + argparse | ~30 |

### REQ-13 用量统计

```python
# engine/usage.py
class UsageTracker:
    """SQLite 存储，按天聚合"""
    # 表: usage(date TEXT, model TEXT, route TEXT,
    #   prompt_tokens INT, completion_tokens INT,
    #   cost REAL, client TEXT, ts DATETIME)
```

- 每次 `_call_model` 返回后记录 token + 按厂商价格算成本
- 前端 `/api/usage` 返回近 7 天汇总，`app.js` 新增用量看板
- 存储用 SQLite（`~/.moa-gateway/usage.db`），避免 jsonl 追加膨胀

### REQ-14 首启引导

- `config.py` 的 `is_first_run()` 判断 → 前端 `app.js` 检测 `/api/status` 的 `is_first_run`
- 若首次：隐藏常规配置页，显示 3 步引导 wizard（选推荐组合 → 填 API Key → 测试连通）
- 向导数据复用 `/api/recommended-combos`，无新增后端接口

### REQ-18 密钥加密

- Windows：用 `win32crypt.CryptProtectData`（DPAPI，用户级密钥）
- macOS/Linux：fallback 到 `cryptography.fernet`（生成密钥存 `~/.moa-gateway/.keyfile`）
- `auth.py` 中 `ensure_api_key`/`get_current_key`/`regenerate_api_key` 增加加解密层
- 兼容迁移：启动时检测旧明文文件，自动加密后覆盖

### REQ-P1 代码签名

- Windows：`signtool.exe`（Windows SDK 自带），需购买代码签名证书
- `build.bat` 中 post-build 步骤：`signtool sign /f cert.pfx /p PASS /t http://timestamp... SuperMOA.exe`
- 无证书时跳过签名但打 WARN 日志

---

## 3. 文件变更清单

| 文件路径 | 操作 | 需求 ID | 说明 |
|----------|------|---------|------|
| `README.md` | 修改 | REQ-01 | 品牌统一为 SuperMOA |
| `requirements.txt` | 修改 | 全局 | 新增依赖 |
| `engine/config.py` | 修改 | REQ-09 | trigger 默认值 strip→rstrip |
| `tests/test_smoke.py` | 修改 | REQ-02 | route_request 解包 3 值 |
| `engine/orchestrator.py` | 修改 | REQ-05,06,15,16,17,21,23,24 | 类型注解+流式合并+清理 |
| `engine/streaming.py` | 修改 | REQ-06 | 调用公共方法 |
| `engine/constants.py` | 新建 | REQ-21 | 魔法数字常量 |
| `tests/test_triggers.py` | 新建 | REQ-03 | 触发词路由 ≥10 用例 |
| `main.py` | 修改/瘦身 | REQ-12 | 拆分至 ≤30 行 |
| `app.py` | 新建 | REQ-12 | FastAPI app 工厂 |
| `routes/chat.py` | 新建 | REQ-12,15 | chat 端点+user_query合并 |
| `routes/admin.py` | 新建 | REQ-12 | 管理端点集合 |
| `engine/log_manager.py` | 新建 | REQ-04,11 | 日志去重+轮转 |
| `engine/usage.py` | 新建 | REQ-13 | 用量统计 |
| `engine/exceptions.py` | 新建 | REQ-24 | 异常规范化 |
| `web/app.js` | 修改 | REQ-07,13,14 | XSS 修复+用量看板+引导 |
| `web/config.html` | 修改 | REQ-14 | 引导向导 UI |
| `tray.py` | 修改 | REQ-22 | 重启竞态修复+品牌 |
| `engine/auth.py` | 修改 | REQ-18 | DPAPI 加密 |
| `engine/profiles.py` | 新建 | REQ-20 | 多配置 profile |
| `LICENSE` | 新建 | REQ-P2 | 开源许可证 |
| `PRIVACY.md` | 新建 | REQ-P4 | 隐私声明 |
| `build.bat` | 修改 | REQ-P1,P6 | 签名+安装包 |
| `scripts/sign.py` | 新建 | REQ-P1 | 签名脚本 |
| `engine/updater.py` | 新建 | REQ-P3 | 版本检查 |

---

## 4. 任务列表

| ID | 任务标题 | 涉及需求 | 依赖 | 复杂度 | 顺序 |
|----|----------|----------|------|--------|------|
| T01 | 基础设施+品牌统一+P0测试修复 | REQ-01,02,09 | 无 | 低 | 1 |
| T02 | 核心引擎重构+流式合并+测试补全 | REQ-03,05,06,15,16,17,21,23,24 | T01 | 高 | 2 |
| T03 | main.py拆分+日志/用量统计+安全修复 | REQ-04,07,10,11,12,13,19 | T02 | 高 | 3 |
| T04 | 托盘修复+密钥加密+首启引导+Profile | REQ-14,18,20,22 | T03 | 中 | 4 |
| T05 | 推广合规+签名+版本更新 | REQ-P1~P6 | T03 | 中 | 5 |

---

## 5. 依赖包列表

```
# 新增
pywin32>=306        # DPAPI 密钥加密（仅 Windows）
cryptography>=42    # 跨平台密钥加密 fallback
openpyxl>=3.1       # 日志 xlsx 导出（已用但未声明）
requests>=2.31      # 版本更新检查
```

---

## 6. 共享知识

| 约定 | 说明 |
|------|------|
| **品牌** | 全部用 `SuperMOA`（非 MOA Gateway），代码注释/日志/UI 统一 |
| **错误处理** | 禁止裸 `except: pass`；用 `engine/exceptions.py` 定义 `UpstreamError`/`ConfigError` 等；所有 except 记日志 |
| **安全取值** | 配置 dict 一律用 `.get(key, default)`，禁止 `[key]` 直取 |
| **日志时间** | 全部用 `datetime.now().isoformat()` 存储，展示时格式化 |
| **API 响应** | 统一 `{code, data, message}` 或 OpenAI 兼容格式 |
| **模块接口** | `orchestrator.call_model()` 为公共方法（去 `_` 前缀），streaming/admin 仅通过公开接口调用 |
| **魔法数字** | 超时/限流/最大日志数等常量放 `engine/constants.py` |

---

## 7. 待明确事项

1. **REQ-18 密钥加密**：DPAPI 需 `pywin32`，是否接受此依赖？还是用 `cryptography` 统一跨平台？
2. **REQ-P1 代码签名**：是否已购买代码签名证书？无证书时仅做 SHA256 校验和？
3. **REQ-P5 错误上报**：是否接入 Sentry/自建？opt-in 门槛（复选框默认关闭）？
4. **REQ-13 用量统计**：是否需要导出 CSV/Excel？还是仅前端看板？
5. **REQ-20 Profile**：profile 存储格式——独立 yaml 文件还是 config.yaml 内嵌多 profile？
6. **许可证选择**：REQ-P2 用 MIT 还是 Apache 2.0？
