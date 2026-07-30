# 🚀 SuperMOA

> **一个 exe，3 个模型参谋，1 个综合答案。**  
> 跑在本地 Windows 上的多模型聚合网关，让 AI 智能体更聪明。

---

## 📖 SuperMOA 是什么

SuperMOA 是一个**跑在你电脑本地**的轻量网关软件。它做的事情很简单：

> 你同时问 3 个 AI 模型同一个问题，SuperMOA 把它们的回答综合起来，给你一个更好的答案。

就像你遇到难题时，同时请教 3 位"军师"，再由一位"统帅"把军师们的意见汇总成最终决策——**集思广益，取长补短**。

### 🎯 30 秒上手

1. **下载** `SuperMOA.exe`，双击运行
2. **配置** 几个 API Key（在网页配置页里填）
3. **开始用** —— 把智能体的 API 地址指向 SuperMOA 即可

就这么简单！👇

---

## ⚡ 快速开始

### 第 1 步：下载并运行

1. 下载 `SuperMOA.exe`（[获取最新版本](#-版本更新)）
2. 双击运行（首次可能遇到杀毒软件提示，详见 [FAQ](docs/faq.md)）
3. 系统托盘出现一个 **蓝色 S 图标** ✅ —— 说明已启动

### 第 2 步：配置 API Key

1. **右键**托盘图标 → 点击「**打开配置页**」
2. 浏览器会自动打开配置页面
3. 点击「**推荐组合**」，选择一个适合你的方案
4. 填入各家模型厂商的 **API Key**（在各厂商官网申请，详见 [FAQ](docs/faq.md)）
5. 点击「**保存**」

### 第 3 步：开始使用

在你的 AI 智能体中设置：

| 设置项 | 值 |
|--------|-----|
| **Base URL** | `http://127.0.0.1:12345/v1` |
| **API Key** | 配置页顶部显示的 `sk-moa-xxxx` |
| **Model** | `SuperMOA` |

完成！现在你的智能体就能享受多模型聚合的威力了 🎉

> 📝 **详细的图文教程**请看 [快速上手指南](docs/quickstart.md)

---

## 🧠 核心概念

### 军师 + 统帅比喻

把 SuperMOA 想象成一个"作战指挥室"：

| 角色 | 对应配置 | 干什么 |
|------|----------|--------|
| 🧙 **军师**（参考模型） | `reference_models` | 3 个 AI 模型，各自独立回答你的问题 |
| 👑 **统帅**（聚合模型） | `aggregator` | 汇总 3 位军师的回答，综合出最终答案 |
| 🏃 **传令兵**（透传模型） | `default_passthrough` | 日常简单问题，直接让一个模型快速回答，不走汇总流程 |

### 工作流程

```
你问了一个问题
       │
       ▼
  SuperMOA 收到请求
       │
       ├── 检查有没有"触发词"
       │
   ┌───┴───────────────────────────┐
   │                               │
   ▼                               ▼
 没触发词                        有触发词
 （传令兵）                       │
   │                        ┌──────┴──────┐
   ▼                        ▼             ▼
 直接调一个模型              hh：          hy3：
 快速返回答案            走军师+统帅     直接调指定军师
                      （3 军师并行→统帅汇总）  （跳过统帅）
```

---

## 🔑 触发词用法

SuperMOA 通过**触发词**来决定怎么处理你的问题。触发词写在消息开头即可：

| 你输入的内容 | 走哪条路 | 效果 |
|-------------|---------|------|
| `帮我写代码` | 🏃 **透传** | 直接调一个模型，快、省钱 |
| `hh：帮我写代码` | 🧙 **MOA 聚合** | 3 个军师并行 + 统帅汇总，质量最高 |
| `hy3：直接回答` | 🏃 **直调** | 跳过统帅，直接调对应模型 |

> 💡 **默认行为**：如果你没配透传模型，所有请求都走 MOA 聚合（质量优先）。

**触发词说明：**
- `hh：` —— 触发多模型聚合（MOA）
- `hy3：` —— 触发直接调用对应参考模型（在配置中定义）
- 触发词包含**中文冒号** `：`（不是英文 `:`）
- 每条消息独立判断，多轮对话中前一轮的触发词不影响后一轮

---

## ⚙️ 配置说明

SuperMOA 的所有配置都在**网页配置页**完成，不需要手动改文件。

### 配置页区域说明

| 区域 | 作用 | 一句话解释 |
|------|------|-----------|
| 🏠 **网关设置** | 设置监听地址和端口 | 默认 `127.0.0.1:12345`，一般不用改 |
| 🧙 **参考模型** | 添加 2-5 个"军师"模型 | 选不同厂商，取长补短效果最好 |
| 👑 **聚合模型** | 设置"统帅"模型 | 综合能力强的模型更适合做统帅 |
| 🏃 **透传模型**（可选） | 设置日常快速响应模型 | 不配的话所有请求都走聚合 |
| 🎚️ **MOA 参数** | 调温度、token 数、超时 | 一般用默认值就行 |
| 📊 **用量看板** | 查看每日 token 消耗和成本 | 心里有数，花钱不慌 |

### 推荐组合

不知道怎么选模型？配置页内置了 3 套推荐组合：

| 组合 | 特点 | 单次成本 |
|------|------|---------|
| 💰 **性价比组合**（推荐） | 日常最划算 | ~¥0.02 |
| 💎 **质量优先组合** | 复杂任务质量最高 | ~¥0.08 |
| 🪙 **极致省钱组合** | 预算紧张也能用 | ~¥0.01 |

> 模型价格仅供参考，以各厂商官网为准。

---

## 🔌 客户端接入

任何支持 OpenAI 兼容 API 的客户端都能接入 SuperMOA。以下是一些常见示例：

### WorkBuddy / Hermes

在设置中找到「自定义模型」或「API 配置」：
- Base URL: `http://127.0.0.1:12345/v1`
- API Key: `sk-moa-xxxx`
- Model: `SuperMOA`

### Cursor

`Settings → Models → OpenAI API →`
- Base URL: `http://127.0.0.1:12345/v1`
- API Key: `sk-moa-xxxx`

### Claude Code

```bash
claude config set baseUrl http://127.0.0.1:12345/v1
claude config set apiKey sk-moa-xxxx
```

### OpenAI Codex CLI

```bash
codex --base-url http://127.0.0.1:12345/v1 --api-key sk-moa-xxxx
```

### Python SDK

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://127.0.0.1:12345/v1",
    api_key="sk-moa-xxxx",
)

# 普通请求（走透传）
resp = client.chat.completions.create(
    model="SuperMOA",
    messages=[{"role": "user", "content": "你好"}],
)

# 走 MOA 聚合（消息开头 hh：）
resp = client.chat.completions.create(
    model="SuperMOA",
    messages=[{"role": "user", "content": "hh：帮我分析这段代码"}],
    stream=True,
)
for chunk in resp:
    print(chunk.choices[0].delta.content or "", end="")
```

---

## ❓ FAQ

> 完整 FAQ 请看 [docs/faq.md](docs/faq.md)

**杀毒软件报毒怎么办？** → 这是 PyInstaller 打包的误报，可加入白名单，详见 FAQ。

**Windows SmartScreen 拦截怎么办？** → 点击「更多信息」→「仍要运行」。

**需要哪些 API Key？多少钱？** → 至少需要 1 个参考模型 + 1 个聚合模型的 Key，推荐组合每天花费约 ¥1-5。

**支持哪些模型？** → DeepSeek、通义千问、腾讯混元、智谱 GLM、MiniMax、小米 MiMo、百度千帆、字节豆包、Moonshot、零一万物等 10+ 厂商。

---

## 🔒 隐私与安全

SuperMOA 非常重视你的隐私：

| 项目 | 措施 |
|------|------|
| 🖥️ **本地运行** | 所有数据处理在本地完成，不上传任何用户数据 |
| 🔐 **API Key 加密** | 使用 Windows DPAPI 加密存储，绑定当前用户账户 |
| 🔒 **仅本地监听** | 默认只监听 `127.0.0.1`，不对外暴露 |
| 🚫 **不收集数据** | 无埋点、无遥测、无行为追踪 |
| 📊 **用量本地存** | 用量统计存在本地 SQLite，不联网上报 |

> 📄 详细的隐私声明请看 [PRIVACY.md](PRIVACY.md)

---

## 📦 从源码运行（开发者）

如果你想从源码运行或参与开发：

```bash
# 1. 克隆仓库
git clone https://github.com/SuperMOA/SuperMOA.git
cd SuperMOA

# 2. 创建虚拟环境
python -m venv .venv
.venv\Scripts\activate

# 3. 安装依赖
pip install -r requirements.txt

# 4. 启动（托盘模式，推荐）
python tray.py

# 或命令行模式
python main.py
```

### 打包成 exe

```bash
# 双击 build.bat 或命令行执行
build.bat
```

输出：`dist/SuperMOA.exe`（约 30-50MB，单文件）

---

## 🧪 测试

```bash
# 冒烟测试（语法 + 路由 + auth + config）
.venv\Scripts\python.exe tests\test_smoke.py

# 触发词路由测试
.venv\Scripts\python.exe tests\test_triggers.py

# 端到端集成测试
.venv\Scripts\python.exe tests\test_e2e.py
```

---

## 📁 项目结构

```
SuperMOA/
├── main.py                 # 命令行入口
├── tray.py                 # 系统托盘程序
├── app.py                  # FastAPI 应用
├── requirements.txt        # 依赖清单
├── build.bat               # 打包脚本
├── README.md               # 本文档
├── CONTRIBUTING.md         # 贡献指南
├── PRIVACY.md              # 隐私声明
├── LICENSE                 # MIT 协议
│
├── engine/                 # 核心引擎
│   ├── constants.py        # 全局常量
│   ├── exceptions.py       # 异常定义
│   ├── vendors.py          # 厂商预置列表
│   ├── config.py           # 配置加载/保存/校验
│   ├── auth.py             # API Key 认证
│   ├── orchestrator.py     # MOA 编排 + 触发词路由
│   ├── streaming.py        # 流式输出
│   ├── health.py           # 健康检查
│   ├── updater.py          # 版本更新检查
│   ├── usage.py            # 用量统计
│   └── profiles.py          # 多配置管理
│
├── routes/                 # API 路由
│   ├── chat.py             # 对话端点
│   └── admin.py            # 管理端点
│
├── web/                    # Web 配置页
│   ├── config.html         # 配置页面
│   └── app.js              # 前端逻辑
│
└── tests/                  # 测试
    ├── test_smoke.py       # 冒烟测试
    ├── test_triggers.py    # 触发词测试
    └── test_e2e.py         # 端到端测试
```

---

## 📜 命令行参数

```bash
SuperMOA.exe [选项]

选项：
  --port N           指定端口（默认 12345）
  --host HOST        指定监听地址（默认 127.0.0.1）
  --regenerate-key   重新生成 API Key
```

---

## 🔄 版本更新

SuperMOA 启动时会自动检查更新（查询腾讯云上的版本信息）。发现新版本时，配置页会显示更新提示。你也可以在配置页手动点击「检查更新」。

更新不会自动下载，需要你手动确认。

---

## 📄 开源协议

本项目基于 **MIT License** 开源。你可以自由使用、修改、分发。详见 [LICENSE](LICENSE)。

---

## 💬 反馈与贡献

- 🐛 **Bug 报告 / 功能建议**：[提交 GitHub Issue](https://github.com/SuperMOA/SuperMOA/issues)
- 💡 **贡献代码**：请阅读 [贡献指南](CONTRIBUTING.md)
- 💬 **交流讨论**：加入微信群（扫码添加）

欢迎 Star ⭐ 支持！

---

## 📚 更多文档

- [快速上手指南](docs/quickstart.md) — 5 分钟从零到能用
- [常见问题 FAQ](docs/faq.md) — 遇到问题先看这里
- [隐私声明](PRIVACY.md) — 数据安全说明
- [贡献指南](CONTRIBUTING.md) — 如何参与开发

---

<p align="center">Made with ❤️ for the AI community</p>
