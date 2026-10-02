# 架构分析技能 v1.0 验收记录

2026-10-02。本地交付范围：技能工作流、机械取证/验证工具、离线交互模板及两个跨结构样例。未修改原订单项目，未访问 ECS、部署或推送远程仓库。

## 结果与证据

| 检查 | 实际结果 | 证据 |
| --- | --- | --- |
| 工具回归 | 20 项通过 | `tests/test_pipeline.py`；命令 `python3 -m unittest discover -s tests -v` |
| 全局技能入口 | 符号链接指向本项目；官方 quick_validate 返回 Skill is valid! | `~/.codex/skills/architecture-audit-canvas` |
| 最终产物绑定 | 两份最终交付 valid=true、无漂移 | validate_artifacts 对 reviewed-model 与 delivery-final 的实际检查 |
| 实现独立审查 | 第二轮通过，第一轮 4+1 项闭合 | [复核记录](implementation-review.md) |
| Python 模型语义 | 独立代理核对 2 节点、1 边、1 风险，通过 | [模型复核](python-demo/semantic-review.md) |
| TypeScript 独立试用 | 独立代理从5个源文件完成2视图、10节点、10边、3风险、3问题 | [试用说明](forward-typescript/forward-test-notes.md) / [尝试记录](forward-typescript/forward-attempt-results.json) |
| TypeScript 模型语义 | 主代理独立于模型作者逐项核对，通过 | [模型复核](forward-typescript/semantic-review.md) |
| Python 最终画布 | 22 项浏览器检查通过，0 脚本错误，离线 0 网络请求 | [浏览器结果](python-demo/browser-final/browser-validation.json) |
| TypeScript 最终画布 | 23 项浏览器检查通过，0 脚本错误，离线 0 网络请求 | [浏览器结果](forward-typescript/browser-final/browser-validation.json) |

浏览器检查包含：视图与目录数量、缩放、平移、适应、节点与边证据、源码片段、链路前进/返回、模块与符号下钻、搜索、返回导航、风险/问题面板、范围说明、窄屏、阻断网络后重新载入。两个样例都实际包含相关节点、边、符号、风险和问题，无以缺元素跳过测试冒充全覆盖的情况。

桌面 1680×1050、窄屏 390×844 截图已实际查看：

- [Python 桌面](python-demo/browser-final/canvas-desktop.png) / [窄屏](python-demo/browser-final/canvas-narrow.png)
- [TypeScript 桌面](forward-typescript/browser-final/canvas-desktop.png) / [窄屏](forward-typescript/browser-final/canvas-narrow.png)

早期浏览器脚本曾在窄屏离线重载后等待隐藏的导航按钮，检查超时；修正测试视口后复验通过。早期输出保留为过程证据，使用 README 中 `delivery-final` 链接作为最终示例。

## 适用边界

1. 两个样例是合成源代码夹具，没有运行被审代码或连接实际后端。配置和注释不代表生产启用。
2. Python 索引是静态 AST；JS/TS 是具名函数词法候选。TypeScript 箭头入队函数由审查模型提供精确引用，不假称机械解析完整。
3. 自动校验确认路径、行号、摘要及模型一致性，不能证明语义。独立审查、最终内容检查和浏览器验证分别保留。
4. 脱敏是保守规则，不保证发现任意秘密/业务数据。审查前识别数据目录，交付前查看实际内嵌内容。
5. 大仓库性能、所有语言、实时调用、外部部署、无障碍全面标准认证不在本次验收范围。
6. 生成 manifest 的 `browser_verified=false` 保留构建时状态；浏览器结果以独立文件中的最终 HTML 摘要关联，不改标志伪造生成时验收。

后续状态更新（2026-10-02）：当前 Codex 项目列表已确认登记为“项目架构可视化”。公开仓库同步另见项目 README 与发布检查记录，不改变本次 v1.0 原始验收范围。
