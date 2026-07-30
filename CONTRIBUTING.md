# 🤝 贡献指南

感谢你对 SuperMOA 的关注！欢迎参与贡献。

---

## 🐛 提交 Issue

### Bug 报告

发现 Bug？请 [提交一个 Bug Issue](https://github.com/SuperMOA/SuperMOA/issues/new?template=bug_report.md)：

1. 使用 Bug 报告模板
2. 尽量详细描述复现步骤
3. 附上环境信息（版本、操作系统、智能体）
4. 如有日志或截图，请一并附上

### 功能建议

有好的想法？请 [提交一个功能建议](https://github.com/SuperMOA/SuperMOA/issues/new?template=feature_request.md)：

1. 使用功能建议模板
2. 描述使用场景和解决的问题
3. 如果有实现想法，也欢迎描述

---

## 🔧 提交 PR

### 开发环境搭建

```bash
# 1. Fork 并克隆仓库
git clone https://github.com/你的用户名/SuperMOA.git
cd SuperMOA

# 2. 创建虚拟环境
python -m venv .venv
.venv\Scripts\activate

# 3. 安装依赖
pip install -r requirements.txt

# 4. 运行测试，确保环境正常
.venv\Scripts\python.exe tests\test_smoke.py
```

### 开发流程

1. **创建分支**：从 `main` 分支创建特性分支
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **编写代码**：遵循下方的代码规范

3. **运行测试**：确保所有测试通过
   ```bash
   .venv\Scripts\python.exe tests\test_smoke.py
   .venv\Scripts\python.exe tests\test_triggers.py
   .venv\Scripts\python.exe tests\test_e2e.py
   ```

4. **提交代码**：编写清晰的 commit message
   ```bash
   git commit -m "feat: 添加 XXX 功能"
   ```

5. **推送并发起 PR**：向 `main` 分支发起 Pull Request

### Commit Message 规范

| 前缀 | 用途 | 示例 |
|------|------|------|
| `feat:` | 新功能 | `feat: 添加流式进度条` |
| `fix:` | Bug 修复 | `fix: 修复多轮对话触发词失效` |
| `docs:` | 文档更新 | `docs: 更新 FAQ` |
| `refactor:` | 重构 | `refactor: 提取公共方法到 orchestrator` |
| `test:` | 测试 | `test: 添加边界情况用例` |
| `chore:` | 杂项 | `chore: 更新依赖版本` |

---

## 📏 代码规范

### 基本约定

- **语言**：代码注释用中文，变量名/函数名用英文
- **类型注解**：所有函数签名添加类型注解（type hints）
- **默认值**：配置 dict 使用 `.get(key, default)`，禁止 `[key]` 直取
- **异常处理**：禁止裸 `except: pass`，使用 `engine/exceptions.py` 定义的异常类
- **常量**：超时、限流等魔法数字放 `engine/constants.py`

### 文件结构约定

```
engine/
├── constants.py    # 全局常量（消除魔法数字）
├── exceptions.py   # 统一异常体系
├── vendors.py      # 厂商预置列表
├── config.py       # 配置加载/保存/校验
├── auth.py          # API Key 认证
├── orchestrator.py  # MOA 编排（核心）
├── streaming.py     # 流式输出
└── ...
```

### 错误处理示例

```python
# ✅ 正确：使用定义的异常类，记日志
from engine.exceptions import UpstreamError, log_and_raise

try:
    resp = client.post(...)
except Exception as exc:
    logger.error("模型调用失败: %s", exc)
    raise UpstreamError(f"模型调用失败: {exc}")

# ❌ 错误：裸 except pass
try:
    resp = client.post(...)
except:
    pass
```

### 配置取值示例

```python
# ✅ 正确：使用 get 带默认值
port = config.get("gateway", {}).get("port", 12345)

# ❌ 错误：直接取值可能 KeyError
port = config["gateway"]["port"]
```

### 新增常量

所有超时、限流、最大数量等参数，统一在 `engine/constants.py` 中定义：

```python
# engine/constants.py
NEW_FEATURE_TIMEOUT = 30  # 新功能超时（秒）

# 使用处
from engine import constants as C
timeout = C.NEW_FEATURE_TIMEOUT
```

---

## 🧪 测试要求

- 新功能必须包含测试用例
- Bug 修复应附带回归测试
- 提交 PR 前确保所有测试通过：

```bash
.venv\Scripts\python.exe tests\test_smoke.py    # 冒烟测试
.venv\Scripts\python.exe tests\test_triggers.py  # 触发词测试
.venv\Scripts\python.exe tests\test_e2e.py       # 端到端测试
```

---

## 💬 交流

- 有问题可以在 [GitHub Discussions](https://github.com/SuperMOA/SuperMOA/discussions) 讨论
- 紧急 Bug 请直接提 Issue

---

感谢你的贡献！🎉
