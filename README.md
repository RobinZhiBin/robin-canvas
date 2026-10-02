# robin-canvas · 架构分析技能

将源码取证、架构评审和交互画布整理成一个可复用的 Codex 技能：`architecture-audit-canvas`。首版 v1.0 已完成本地实现、独立复核、跨结构试用与浏览器验收。

它读取项目代码与配置，形成证据模型，再生成三份同源交付：一个可离线打开的 HTML 画布、一份架构剖析报告、一份待确认问题清单。它不执行被审项目，不根据配置推断真实运行状态。

## 从这里开始

- [技能入口](skills/architecture-audit-canvas/SKILL.md)
- [交互示例：TypeScript 提交与后台处理](output/forward-typescript/delivery-final/architecture-canvas.html)
- [对应剖析报告](output/forward-typescript/delivery-final/architecture-report.md) / [待确认问题](output/forward-typescript/delivery-final/open-questions.md)
- [简短示例：Python 接收与保存](output/python-demo/delivery-final/architecture-canvas.html)
- [验收证据与能力边界](output/acceptance-v1.md) / [任务清单](TODO.md)

在 Codex 中使用：

```text
使用 $architecture-audit-canvas 对当前项目做严格架构剖析。
覆盖所有模块，重点追踪登录、上传识别和订单发送的完整生命周期。
先读取代码与配置，每个确定节点和连线都提供文件及行号。
未确认行为单独列明，生成离线交互画布、剖析报告和待确认清单。
只读分析，不修改被审项目，不访问生产或外发数据。
```

专项分析时改为具体链路即可；已有画布更新时同时提供旧快照/模型目录。只问问题或先规划时，技能走只读咨询流程，不自动生成文件。

## 首版提供什么

| 能力 | 实现与边界 |
| --- | --- |
| 全局目录与逐层下钻 | 文件目录、业务视图、模块、函数与引用片段；索引和语义审查状态分开 |
| 链路追踪 | 沿证据模型前进/返回，查看每条边依据；不是运行时调用栈回放 |
| 交互画布 | 缩放、平移、适应窗口、宽幅、搜索、风险和问题面板、窄屏抽屉 |
| 证据基线 | Git 状态、未跟踪文件、内容摘要、引用行号、排除项；构建前后核对漂移 |
| 风险评审 | 事实、影响、建议分开；汇总路径保留中间步骤；未知/冲突显式标注 |
| 内容控制 | 不内嵌未审查文件全文；保守脱敏引用片段，交付前仍需人工检查 |
| 一致性验证 | 模型、画布、报告及 manifest 绑定；旧图不能拿新模型验证通过 |

Python 使用标准库 AST 提取静态定义/导入/调用表达式。JS/TS 只自动索引具名函数词法候选，箭头函数、动态调用和其他语言的语义由审查补证。不能据此宣称“所有语言自动生成完整调用图”。

## 项目结构

```text
skills/architecture-audit-canvas/
  SKILL.md                         触发条件、工作流程与调用方法
  agents/openai.yaml               Codex 技能展示入口
  references/                     证据、审查、验收规范
  scripts/collect_snapshot.py       源码与配置快照
  scripts/check_drift.py            已有快照变更检查
  scripts/build_canvas.py           离线画布和报告生成
  scripts/validate_artifacts.py     模型及生成物校验
  scripts/audit_core.py             共享取证与校验函数
  scripts/browser_smoke.js          通用真实浏览器检查
  assets/canvas-template.html       无 CDN 的离线模板
tests/                             合成夹具及工具回归检查
output/                            示例、独立试用、复核与浏览器证据
```

项目脚本只依赖 Python 3.10+ 标准库。生成好的 HTML 无需 Python、服务端或网络；浏览器验收另外使用本机已安装的 Playwright CLI 和 Chrome，不自动安装依赖。

```sh
python3 -m unittest discover -s tests -v
python3 tests/browser_check.py output/forward-typescript/delivery-final output/browser-recheck
```

具体取证和生成命令见技能入口。输出使用新目录，保留旧版本。真实项目开始前先识别业务数据目录并排除；默认命名规则无法识别所有客户数据。

## 安装与维护

仓库：[RobinZhiBin/robin-canvas](https://github.com/RobinZhiBin/robin-canvas)。正式源码在本项目的 `skills/architecture-audit-canvas/`，技能名称保持 `architecture-audit-canvas`。

维护机的全局发现入口采用 `~/.codex/skills/architecture-audit-canvas` 符号链接指向本项目技能目录，避免两个版本分别维护。其他使用者可克隆仓库后，将该技能目录注册到自己的 Codex 技能目录；使用 `$architecture-audit-canvas` 调用，必要时新建会话刷新技能列表。

公开内容包含技能源码、合成测试夹具、两个 `delivery-final` 示例及对应验收证据。早期重复交付、失败浏览器日志和其他审计输出保留在维护机本地，不进入公开提交。示例中的快照记录生成时的 Git 状态；克隆或提交后如需重新审计，应采集新快照，不改写历史验收证据。

后续优先收集真实项目使用反馈，再决定是否增加语言解析器、自动布局优化或差异视图。首次交付没有承诺大仓库性能指标，也没有将测试样例当成生产系统验收。
