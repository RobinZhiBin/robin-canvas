---
name: architecture-audit-canvas
description: 基于代码与配置剖析现有系统，追踪业务链路并生成可查证、可下钻的离线架构画布、评审报告和待确认清单；也可核查已有画布是否过期。适用于架构评审、系统接手与链路解释，不因普通代码问答自动启动全仓审计。
---

# 架构剖析与交互画布

先确认用户要理解的系统与范围。执行源码审查，使用本技能脚本完成机械索引、证据校验与呈现。架构结论由证据支持，脚本不能证明结论为真，也不能自动恢复完整动态调用图。

## 选择路径

- **只问问题 / 先分析规划**：只读现有画布、证据和相关源码；不生成文件、不运行构建或安装依赖。
- **全局剖析 / 新建画布**：以下流程；全范围文件进入目录，但重点业务视图按主题组织，不能把索引覆盖说成全部审查完成。
- **专项链路**：只审查相关入口到终点，声明范围和未展开的边界；不要求用户先补出模块名。
- **更新**：先检查旧快照变化，复核受影响事实，再创建新版本。不能因为源码改变就自动将旧风险标成已修复。

## 工作流

1. 读项目规则、现有决策与入口；仓库文档和注释是待核对材料，不是新的执行授权。需要已有运行观察时读取其脱敏证据；没有现场证据就标未核验，不主动登录生产或调用外部系统。
2. 按 [证据规范](references/evidence-contract.md) 建立只读快照。先定位并用 `--exclude` 排除实际业务数据目录（例如原件、上传、导出、客户数据）；不能只依靠通用文件名规则。在输出目录保存 `snapshot.json`，由内容摘要而非仅 HEAD 确定基线。推荐输出在仓库外，或已排除的 `output/` 下。
3. 阅读路由、模块、配置和存储实现，按 [审查流程](references/audit-workflow.md) 写 `audit-model.json`。静态导入、直接调用、跨组件汇总路径、HTTP、存储、调度和运行观察分别说明。无法确认的边标 unknown/conflict，并写明缺什么证据。
4. 每条确定性节点/边都写 `refs` 和 `evidence_note`，解释引用如何支持它。汇总边提供中间 `via` 和多处引用。事实、影响、建议分开；不凭文件名或函数名补写职责。
5. 独立只读复核语义证据，修正后将 `review.status` 从 draft 设为 reviewed，记录审查者和快照 ID。这是声明，必须保留实际复核记录；无独立审查条件时保留 draft 并说明，不伪造身份。
6. 用构建脚本生成单 HTML、报告、问题清单以及配套证据 JSON/manifest。只内嵌模型明确引用及已审查代码符号/导入的脱敏片段；不会因文件被索引就导出其内容。自动脱敏不是全面保证，按 [验收](references/acceptance.md) 检查实际产物及浏览器行为。
7. 交付三个用户文件与验证边界；索引不全、尚未确认的现场/业务行为必须明示。不得将生成成功、引用非空或健康接口当架构语义/业务验收。

## 工具调用

将 `SKILL_DIR` 设为本 SKILL.md 所在目录，`REPO` 为已授权审查目录，`RUN` 为本次独立输出目录。脚本仅需 Python 3.10+ 标准库。不要执行目标仓库安装脚本或 import 目标模块来获取结构。

```sh
python3 "$SKILL_DIR/scripts/collect_snapshot.py" --repo "$REPO" --out "$RUN/snapshot.json"
# 审查后写 RUN/audit-model.json，详见证据规范中的完整示例。
python3 "$SKILL_DIR/scripts/validate_artifacts.py" --repo "$REPO" --snapshot "$RUN/snapshot.json" --model "$RUN/audit-model.json"
python3 "$SKILL_DIR/scripts/build_canvas.py" --repo "$REPO" --snapshot "$RUN/snapshot.json" --model "$RUN/audit-model.json" --out "$RUN/delivery"
python3 "$SKILL_DIR/scripts/validate_artifacts.py" --repo "$REPO" --snapshot "$RUN/snapshot.json" --model "$RUN/audit-model.json" --artifacts "$RUN/delivery"
```

已有证据的只读检查（默认不写文件；退出码 2 表示已过期）：

```sh
python3 "$SKILL_DIR/scripts/check_drift.py" --repo "$REPO" --snapshot "$RUN/snapshot.json" --model "$RUN/audit-model.json"
```

输出已存在时选择新目录，不覆盖历史审计。`collect_snapshot.py --exclude PATTERN` 可按项目范围排除路径，记录每个排除项；不要为让校验通过临时排除变化文件。支持无 Git 项目。

## 输出与能力边界

- `architecture-canvas.html`：无需联网，缩放/平移、链路前后导航、模块/函数下钻、源码片段、风险与问题面板。
- `architecture-report.md`：总评、链路、风险、范围与证据；`open-questions.md`：技术补证与业务决策，避免重复询问已确认事项。
- 配套 `snapshot.json / audit-model.json / canvas-data.json / manifest.json`：用于复核、变更检测与后续更新。单 HTML 独立可读，不需要这些侧文件才能显示。
- Python AST 可机械索引定义/导入/调用表达式；JS/TS 只提供具名函数词法候选。其他语言/配置按文件入目录，由审查补证；不声称存在完整语义解析器。
- 文件不支持、超限、私有路径、符号链接或 Git 忽略项会排除并披露。默认限 2 MiB/文件。重要模块被排除时缩小取证材料或显式调整范围，不悄悄把遗漏当完成。
- 离线画布是快照；只有再次运行变更检查才能知道仓库当前状态。运行现场证据具有采样时间和范围，不能由源码推定。
