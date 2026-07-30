# MOA Gateway 全球方案调研报告

> 调研时间：2026-07-27
> 调研范围：MOA 概念溯源、OpenAI 兼容网关、多模型聚合、命令路由设计、本地工程实践
> 调研方法：WebSearch + WebFetch（GitHub / arXiv / 官方文档）

---

## 一、MOA 概念溯源

### 1.1 MOA 是 Together AI 的概念

**Mixture of Agents (MoA)** 由 Together AI 于 2024 年 6 月提出，论文《Mixture-of-Agents Enhances Large Language Model Capabilities》(arXiv:2406.04692)，开源实现 [github.com/togethercomputer/MoA](https://github.com/togethercomputer/MoA)。

**核心思想**：
- **分层架构**：每层含多个 LLM agent，agent 接收上一层所有输出作为辅助信息，生成 refine 后的响应
- **Proposers**：并行生成初始参考响应（提供多样性视角）
- **Aggregators**：综合多个 Proposer 的响应，输出更高质量的最终答案
- **collaborativeness 现象**：LLM 看到其他模型的输出后，即使那些模型更弱，也能生成更好的响应

**Together MoA 参考实现**：
- 6 个开源模型作 Proposer：WizardLM-2-8x22b、Qwen1.5-110B、Qwen1.5-72B、Llama-3-70B、Mixtral-8x22B、DBRX
- Qwen1.5-110B-Chat 作最终 Aggregator
- **3 层架构**
- AlpacaEval 2.0 上 65.1%，超 GPT-4o 的 57.5%

### 1.2 与我们实现的对比

| 维度 | Together MoA | 我们的 MOA Gateway |
|------|-------------|-------------------|
| 层数 | 3 层（迭代 refine）| 1 层（proposer + aggregator）|
| Proposer 数 | 6 个 | 2-5 个（可配）|
| 模型来源 | 自部署开源模型 | 商业 API（DeepSeek/通义等）|
| 路由 | 无（全走 MOA）| `/hh` 命令路由 + 透传 |
| 部署 | 研究/ demo | 本地生产（exe + 托盘）|
| 流式 | 部分支持 | 全支持（含 fallback 伪造 SSE）|

**结论**：我们的实现是 MOA 的**单层简化版**，加了工程化（`/hh` 路由 + 透传 + Web 配置 + 托盘）。Together MoA 偏研究，我们偏生产。

---

## 二、重点竞品对比

### 2.1 LiteLLM（litellm-proxy）

- **仓库**：[litellm.ai](https://www.litellm.ai/) / [docs](https://docs.litellm.ai/docs/routing-load-balancing)
- **规模**：240M+ Docker pulls，1B+ requests served，1005+ contributors，Netflix/Lemonade 在用
- **技术栈**：Python，YC 项目
- **核心特性**：
  - 100+ LLM Provider 集成
  - **5 种路由策略**：simple-shuffle / least-busy / latency-based / cost-based / usage-based
  - **Fallback 链**：provider failover，cooldowns/retries
  - **自动路由（语义路由）**：用 embedding 分类请求，路由到最适合的模型
  - **标签路由**：多租户隔离
  - **健康检查驱动路由**：后台健康检查，主动剔除故障部署
  - **成本追踪**：按 key/user/team/org 维度
  - **限流**：RPM/TPM
  - **缓存**：Redis
  - **可观测性**：Langfuse/Langsmith/Arize/OTEL
  - **Guardrails**、Prompt Management、S3 Logging
  - **Virtual Keys**、Budgets、Teams

### 2.2 One API（songquanpeng）

- **仓库**：[github.com/songquanpeng/one-api](https://github.com/songquanpeng/one-api)
- **技术栈**：Go + React，单二进制
- **核心特性**：
  - 30+ 模型厂商（OpenAI/Azure/Claude/Gemini/DeepSeek/豆包/ChatGLM/文心/星火/通义/360/混元/Moonshot/百川/MINIMAX/Groq/Ollama/零一/阶跃/Coze/Cohere/Cloudflare/xAI 等）
  - **多渠道负载均衡**
  - **令牌管理**：过期时间、额度、IP 范围、模型限制
  - **兑换码系统**、用户分组、渠道分组、倍率
  - **模型映射**（重定向请求模型名）
  - **失败自动重试**
  - **多机部署**（Redis 协调 RPM/TPM）
  - **Cloudflare AI Gateway** 支持
  - **Cloudflare Turnstile** 用户校验
  - 多种登录（邮箱/GitHub/飞书/微信公众号）
  - 绘图接口、自定义首页

### 2.3 New API（QuantumNous/Calcium-Ion）

- **仓库**：[github.com/QuantumNous/new-api](https://github.com/QuantumNous/new-api)（One API 二开）
- **核心增强**：
  - **渠道加权随机**
  - **缓存计费**（OpenAI/Azure/DeepSeek/Claude/Qwen 等缓存命中按比例计费）
  - **Reasoning Effort 后缀**：`o3-mini-high` / `claude-3-7-sonnet-thinking` / `gemini-2.5-pro-thinking-128`
  - **格式转换**：OpenAI ⇄ Claude Messages ⇄ Gemini Chat（Claude Code 调第三方模型）
  - **思考转内容**功能
  - **Rerank 模型**（Cohere/Jina）
  - **OpenAI Realtime API / Responses 格式**
  - **数据看板**
  - **用户级模型限流**
  - 在线充值（易支付/Stripe）

### 2.4 SynapseHub

- **仓库**：[github.com/hikariming/synapsehub](https://github.com/hikariming/synapsehub)
- **核心特性**：基于 Token 的模型动态选择、密钥熔断（异常流量自动熔断）、多租户隔离、对话审计
- **技术栈**：Node.js + MongoDB + Redis

### 2.5 rayxiu/Mixture-of-Agents

- **仓库**：[github.com/rayxiu/Mixture-of-Agents](http://github.com/rayxiu/Mixture-of-Agents)
- **核心**：Claude Sonnet 3.5 + Gemini 1.5 Pro + GPT-4o 的 MOA 实现，偏 demo

### 2.6 综合对比表

| 项目 | Star/规模 | 核心定位 | 技术栈 | 与我们的差异 | 可借鉴点 |
|------|----------|---------|--------|------------|---------|
| **Together MoA** | 学术 + 开源 | MOA 概念起源 | Python | 多层、研究向 | 多层 refine 思路（可选）|
| **LiteLLM** | 240M+ pulls | 企业 LLM 网关 | Python | 100+ provider、5 种路由 | 路由策略、fallback 链、健康检查 |
| **One API** | 万级 Star | OpenAI 兼容代理 | Go | 多渠道、令牌管理、多机 | 令牌管理、模型映射、失败重试 |
| **New API** | 万级 Star | One API 增强 | Go | 加权随机、格式转换、缓存计费 | 加权随机、模型名后缀路由 |
| **SynapseHub** | 较少 | 智能路由网关 | Node.js | 密钥熔断、Token 动态选择 | 密钥熔断 |
| **我们** | MVP | 本地 MOA + /hh 路由 | Python | 单机、托盘、Web 配置 | /hh 命令路由是独特设计 |

---

## 三、设计模式借鉴

### 3.1 路由策略

**LiteLLM 的 5 种策略**：
1. `simple-shuffle`：随机（默认，性能最好）
2. `least-busy`：最少活跃请求
3. `latency-based-routing`：历史延迟优先
4. `cost-based-routing`：成本优先
5. `usage-based-routing`：RPM/TPM 使用率优先

**我们的现状**：只有透传 vs MOA 二选一，参考模型全部并行调用。

**可借鉴**：
- 参考模型并行调用前，可加 `latency-based` 筛选（只调最近响应快的 3 个）
- 但 MVP 阶段不必要——并行全调更简单，且 MOA 的价值在于多样性，按延迟筛选会损失多样性

### 3.2 Fallback 与容错

**LiteLLM**：A 失败 → cooldown → 自动切 B，num_retries 可配
**One API**：失败自动重试，渠道间 fallback
**我们**：`degraded_policy`（loud 告知聚合模型 / silent 静默跳过）

**可借鉴**（P1）：
- 当前 loud 模式把错误塞进聚合 prompt，可能污染聚合质量
- 改进：参考模型失败时，**重试一次**（参考 LiteLLM num_retries=2）
- 仍失败再按 degraded_policy 处理

### 3.3 缓存层

**LiteLLM**：Redis 缓存 + 语义缓存
**One API/New API**：Redis 缓存 + 内存缓存
**我们**：无缓存

**可借鉴**（P2）：
- 简单内存缓存：相同 prompt（hash messages）在 N 分钟内直接返回缓存结果
- 仅对**透传模式**启用（MOA 模式每次都要多模型参谋，缓存意义小）
- 注意：缓存要排除 stream 请求的中间状态，只缓存最终内容

### 3.4 成本控制

**LiteLLM**：按 key/user/team/org 追踪 token 消耗 + 预算上限
**One API**：令牌额度 + 倍率 + 兑换码
**我们**：usage 字段只算聚合模型 token

**可借鉴**（P2）：
- 加请求日志（route/passthrough/moa、参考模型成功失败数、总耗时、token 消耗）
- 落盘到 `~/.moa-gateway/requests.log`，配置页可查
- 不做预算上限（本地单用户没必要）

### 3.5 可观测性

**LiteLLM**：Langfuse/Langsmith/Arize/OTEL 集成
**One API**：日志 + 数据看板
**我们**：stdout 日志

**可借鉴**（P1）：
- 加 `/api/logs` 端点，返回最近 N 条请求日志
- 配置页加"请求历史"卡片
- 不接外部可观测性平台（本地版过重）

### 3.6 限流

**LiteLLM**：RPM + TPM 双维度
**我们**：仅 IP 维度 RPM（60/min）

**可借鉴**（P2）：
- 加 TPM（每分钟 token 数）限流，防止单请求刷爆上游
- 但本地单用户场景，IP 限流够用

### 3.7 健康检查

**LiteLLM**：后台健康检查，主动剔除故障部署
**我们**：无（请求时才知道失败）

**可借鉴**（P1）：
- 启动时对每个配置的模型发 ping 请求，标记可用/不可用
- 配置页"测试连接"按钮已有此能力，可复用
- 后台定时（每 5 分钟）健康检查，不可用的模型在 MOA 调度时跳过

---

## 四、/hh 命令路由的同类设计

### 4.1 没找到完全相同的设计

搜遍了 LiteLLM、One API、New API、SynapseHub，**没有项目做"消息前缀触发不同模型/模式"**。

最接近的几个设计：

| 项目 | 设计 | 与 /hh 的差异 |
|------|------|--------------|
| **New API** | 模型名后缀：`o3-mini-high`、`claude-thinking` | 改的是 model 字段，不是消息内容 |
| **LiteLLM** | 标签路由：请求带 `tags: ["paid"]` | 改的是 metadata，不是消息内容 |
| **LiteLLM** | 自动路由（语义路由）：用 embedding 分类 | 自动判断，不是显式命令 |
| **One API** | 令牌后缀渠道 ID：`Bearer KEY-CHANNEL_ID` | 改的是 Auth header |

### 4.2 /hh 的独特价值

我们的 `/hh` 是**用户侧显式控制**：
- 优点：用户精确控制何时走 MOA（省钱）、何时走聚合（求质量）
- 优点：不依赖 embedding 模型，零额外成本
- 优点：兼容所有 OpenAI 客户端（不需要客户端支持 metadata/tags）
- 缺点：用户要记住命令
- 缺点：消息开头被污染（虽已剥离，但用户输入时有感知）

### 4.3 可扩展方向

借鉴 New API 的后缀思路，未来可加更多前缀命令：
- `/hh` → MOA（已实现）
- `/hh-fast` → 只调最快的 1 个参考模型 + 聚合（省时）
- `/hh-deep` → 2 层 MOA（Together MoA 风格，质量更高但更慢）
- `/hh-cheap` → 只调最便宜的参考模型

实现成本：在 `engine/orchestrator.py` 的 `route_request` 加前缀解析分支即可。

---

## 五、工程实践借鉴

### 5.1 打包分发

| 项目 | 方案 | 我们 |
|------|------|------|
| One API | Go 单二进制（~20MB）| Python PyInstaller（~30-50MB）|
| LiteLLM | Docker 为主 | PyInstaller exe |
| New API | Docker 为主 + Electron 桌面端 | PyInstaller exe |

**借鉴**（P2）：Go 的单二进制比 Python PyInstaller 更轻、启动更快。但重写代价大，MVP 阶段保持 Python。

### 5.2 配置管理

| 项目 | 方案 | 我们 |
|------|------|------|
| LiteLLM | YAML config + Admin UI | YAML + Web 配置页 |
| One API | 数据库（SQLite/MySQL）+ Web UI | YAML 文件 |
| New API | 数据库 + Web UI + 数据看板 | YAML 文件 |

**借鉴**：
- 我们的 YAML + Web 配置页对本地单用户够用
- 如果未来要多用户/多机，再上 SQLite
- **不建议**现在引入数据库（增加复杂度，本地版不需要）

### 5.3 多机部署

**One API**：Redis 协调多实例 RPM/TPM
**LiteLLM**：Redis 共享限流数据
**我们**：单机，不需要

**不建议借鉴**：本地版单机够用，多机部署是云端版的事。

### 5.4 模型映射

**One API**：模型名重定向（用户发 `gpt-4`，实际调 `deepseek-v4`）
**我们**：任意 model 都接受，不校验

**可借鉴**（P2）：
- 加模型映射表：客户端发 `model: "moa-fast"` → 路由到特定配置
- 但 `/hh` 已经够了，模型映射是另一种思路，可选

### 5.5 格式转换

**New API**：OpenAI ⇄ Claude Messages ⇄ Gemini Chat
**我们**：仅 OpenAI 兼容

**可借鉴**（P1，如果有需求）：
- 如果用户想把 Claude Code 接入（Claude Code 用 Anthropic 协议），需要 OpenAI → Claude Messages 转换
- 但 Claude Code 支持自定义 baseUrl（OpenAI 兼容），所以暂不需要

---

## 六、可借鉴点清单（按优先级）

| # | 借鉴点 | 来源项目 | 对我们的改进 | 优先级 | 工作量 |
|---|--------|---------|------------|--------|--------|
| 1 | **参考模型失败重试** | LiteLLM | 失败时重试 1 次再降级，提升成功率 | P0 | 0.5天 |
| 2 | **后台健康检查** | LiteLLM | 启动 + 定时 ping 模型，不可用的跳过 | P0 | 0.5天 |
| 3 | **请求日志 + 配置页查看** | One API | 落盘 route/耗时/token，配置页可查 | P1 | 1天 |
| 4 | **透传模式响应缓存** | LiteLLM | 相同 prompt N 分钟内返回缓存 | P1 | 0.5天 |
| 5 | **TPM 限流** | LiteLLM | 加 token/min 维度，防刷爆 | P2 | 0.5天 |
| 6 | **/hh 扩展命令** | New API 后缀思路 | `/hh-fast` `/hh-deep` 等变体 | P2 | 0.5天 |
| 7 | **模型映射表** | One API | `model` 字段路由到不同配置 | P2 | 0.5天 |
| 8 | **密钥熔断** | SynapseHub | 异常流量自动熔断 key | P3 | 1天 |
| 9 | **多层 MOA** | Together MoA | `/hh-deep` 触发 2 层 refine | P3 | 1天 |

---

## 七、不建议借鉴的点

| # | 不借鉴 | 原因 |
|---|--------|------|
| 1 | **数据库（SQLite/MySQL）** | 本地单用户过重，YAML 够用 |
| 2 | **多机部署 / Redis** | 本地版不需要，云端版再考虑 |
| 3 | **语义路由（embedding 分类）** | 需要 embedding 模型，成本高，`/hh` 显式命令更简单可靠 |
| 4 | **在线充值 / 用户管理 / 兑换码** | 本地版不需要商业化能力 |
| 5 | **复杂格式转换（OpenAI ⇄ Claude ⇄ Gemini）** | 主流客户端都支持 OpenAI 兼容，暂不需要 |
| 6 | **Docker 部署** | 本地 Windows 用户双击 exe 更友好 |
| 7 | **外部可观测性平台集成** | Langfuse/Langsmith 对本地版过重 |
| 8 | **默认多层 MOA** | 延迟翻倍，MVP 单层够用，`/hh-deep` 作为可选 |

---

## 八、结论与建议

### 8.1 我们的定位

我们的 MOA Gateway 在全球范围内**定位独特**：
- Together MoA 偏研究（多层、自部署模型）
- LiteLLM/One API/New API 偏企业网关（多用户、多机、商业化）
- **我们是本地单用户的生产工具**（exe + 托盘 + Web 配置 + `/hh` 命令路由）

`/hh` 命令路由是**没有先例的设计**，是我们的差异化亮点。

### 8.2 立即建议（P0，1 天内可完成）

1. **参考模型失败重试**：当前 loud 模式把错误塞进聚合 prompt 会污染质量。改为失败时重试 1 次，仍失败再降级。
2. **后台健康检查**：启动时 + 每 5 分钟 ping 各模型，不可用的在 MOA 调度时跳过，配置页显示状态。

### 8.3 短期建议（P1，2-3 天）

3. **请求日志**：落盘 route/参考模型成功失败数/总耗时/token，配置页加"请求历史"卡片。
4. **透传响应缓存**：相同 prompt（hash）5 分钟内返回缓存，省上游费用。

### 8.4 中期建议（P2，按需）

5. `/hh-fast` / `/hh-deep` 命令变体
6. TPM 限流
7. 模型映射表

### 8.5 不建议做的事

- 不要为了"对齐 LiteLLM"就加数据库、多机、语义路由——本地版不需要
- 不要把 MOA 改成多层默认——延迟翻倍不划算，作为 `/hh-deep` 可选
- 不要加商业化能力（充值、用户管理）——不是这个项目的目标

### 8.6 与现有代码的对应关系

| 借鉴点 | 现有代码位置 | 改动方式 |
|--------|------------|---------|
| 失败重试 | `engine/orchestrator.py:moa_round` | gather 后对失败的 ref 重试 1 次 |
| 健康检查 | 新增 `engine/health.py` | 启动 + 定时线程，结果存内存 |
| 请求日志 | `main.py:chat_completions` | 加 logging + `/api/logs` 端点 |
| 透传缓存 | `engine/orchestrator.py:passthrough` | 加内存 dict + TTL |
| /hh 变体 | `engine/orchestrator.py:route_request` | 加前缀解析分支 |
| TPM 限流 | `engine/auth.py:check_rate_limit` | 加 token 计数 |

---

## 附录：调研来源

1. Together AI MoA 论文：https://arxiv.org/abs/2406.04692
2. Together MoA 开源：https://github.com/togethercomputer/MoA
3. Together MoA 博客：https://www.together.ai/blog/together-moa
4. LiteLLM 官网：https://www.litellm.ai/
5. LiteLLM 路由文档：https://docs.litellm.ai/docs/routing-load-balancing
6. One API：https://github.com/songquanpeng/one-api
7. New API：https://github.com/QuantumNous/new-api
8. SynapseHub：https://github.com/hikariming/synapsehub
9. rayxiu/Mixture-of-Agents：https://github.com/rayxiu/Mixture-of-Agents
