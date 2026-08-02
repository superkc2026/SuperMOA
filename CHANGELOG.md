# Changelog

All notable changes to SuperMOA will be documented in this file.

## [Unreleased] - 2026-08-03

### Added
- CHANGELOG.md（本文件）
- 统一错误响应格式：所有 API 端点返回 `{error: {code, message, type}}`
- 接口幂等设计：chat/completions 端点支持 request_id 防重复提交
- 安全审计日志：记录 API Key 重新生成 / 配置导出导入等敏感操作
- ADR 文档：3 条架构决策记录（触发词路由选型、流式合并方案、main.py 拆分策略）
- Semgrep SAST 扫描配置（.semgrep.yml）
- Trivy 依赖漏洞扫描配置
- Gitleaks 密钥检测配置（.gitleaks.toml）
- GitHub Actions CI（语法检查 + 测试）
- Gitea→GitHub 自动镜像（post-receive hook）

### Changed
- 无

### Fixed
- 无

## [1.0.0] - 2026-07-30

### Added
- 多模型聚合（MOA）：2-5 个参考模型并行 + 1 个聚合模型综合
- 触发词路由：无触发词走透传，hh：走 MOA，hy3：走直接调用
- Web 配置页 + 系统托盘后台运行
- 用量统计 + 成本估算（SQLite）
- 多配置方案（Profile）切换
- 首启引导向导（3 步）
- 版本更新检查（查腾讯云 versions.json）
- API Key 加密存储（DPAPI + Fernet fallback）
- 错误上报 opt-in（本地存储脱敏堆栈）
- 隐私保护（本地运行，不外传数据）
- 错误提示友好化（friendly_error_message）
- 概念说明步骤（智囊团比喻）
- 配置页 tooltip
- 日志轮转（10MB 滚动，保留 3 份）
- 日志去重修复（time.time() 替代 strptime 比较）
- httpx 连接池复用
- main.py 拆分（780→52 行，拆为 app.py + routes/chat.py + routes/admin.py）
- 流式/非流式逻辑合并（gather_references + build_agg_prompt 公共方法）
- /hh 死代码清理
- 魔法数字常量化（engine/constants.py）
- 异常规范化（engine/exceptions.py）
- model_cfg 安全取值（.get() 带默认）
- XSS 漏洞修复（escapeHtml）
- trigger 默认值 bug 修复（strip→直接拼接）
- config export 脱敏
- 密钥加密存储（DPAPI）
- MIT 开源许可证
- 隐私声明（PRIVACY.md）
- 贡献指南（CONTRIBUTING.md）
- GitHub Issue 模板
- 快速上手指南（docs/quickstart.md）
- FAQ（docs/faq.md）
- README 重写（面向新用户）
- supermoa-setup skill（引导式安装教程）
- 腾讯云 CloudBase 静态托管部署（落地页 + versions.json + exe 下载）
- 落地页 index.html（产品介绍 + 下载按钮 + SHA256 校验）
- 打包 SuperMOA.exe v1.0.0（29MB，PyInstaller）
- SHA256 校验和

### Changed
- 品牌名从 "MOA Gateway" 统一为 "SuperMOA"
- 路由机制从 /hh 命令改为触发词切换
- updater.py 从查 GitHub Release 改为查腾讯云 versions.json

### Fixed
- test_smoke.py 崩溃（route_request 返回 3 值，测试解包 2 值）
- _call_model 类型注解错误（-> Tuple[str, dict] 实际返回 3 元组）
- 流式/非流式逻辑重复约 80%
- 日志去重时间比较失效（datetime.now() vs strptime 差 125 年）
- trigger 默认值 bug（strip("：") 双向剥离）
- XSS 漏洞（loadLogs/renderUsage 未转义）
- httpx 客户端未复用（每次请求新建）
- logs.jsonl 无限增长
- main.py 780 行职责过载
- /hh 半死代码
- 裸 except 吞异常
- 首启引导 bug（is_first_run 检查 config.yaml 但 ensure_config 启动时已创建）
