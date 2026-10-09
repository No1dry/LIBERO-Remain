# 当前协作状态

更新：2026-10-09（Codex 独立审查通过）。代码：X；代码与实验审查：Codex；实验执行：DeepSeek。

## 当前大阶段

Stage 01：精简指标展示、建立人工 UIR 标注与汇总，并集成已验证的 venv 解释器修复。
阶段状态：accepted，待 PR #1 合并及发布版本核验后 closed。暂不启动新的正式 GPU 评测。

| 任务 | 执行者 | 状态 | 入口 | 交付/裁决 |
|---|---|---|---|---|
| 001 指标展示与人工 UIR | X | accepted | [任务](tasks/001_metrics_and_uir.md) | [PR #1](https://github.com/No1dry/LIBERO-Remain/pull/1)、[回应](responses/001_round1.md)、[Codex review](reviews/stage01_round1.md) |
| 002 venv 解释器路径修复 | X | accepted | [任务](tasks/002_venv_interpreter.md) | 同一 PR；[回应](responses/002_round1.md)、[Codex review](reviews/stage01_round1.md) |
| 003 官方/Remain 00 回归入口 | X | open | [任务](tasks/003_normal00_regression_entry.md) | Stage 02；待代码交付与审查 |

实现提交 `46d935b1b8e8109bbc840a2e4347ed520cdd4df7`，分支 `x/stage01-metrics-uir-venv`。
X 回归 982 passed / 15 skipped；Codex 独立 macOS 985 passed / 12 skipped、Linux 986 passed / 11 skipped，
真实历史 OFT 数据只读派生与旧分数不变已核验。代码功能已验收，X 获准按 review 合并 PR、登记 main SHA。
当前实现尚未发布到 main，X 不自行宣告阶段 closed。

Stage 01 的[总结](../docs/stage_summaries/stage_01_metrics_uir.md)已写并本地归档；合并后再确认最终版本。
下一步先对旧四视频做人工 UIR 校准，再审任务 003；DeepSeek 只做模板/报告操作及之后的固定 00 回归。

## 已关闭阶段

- Stage 00：[首次真实 OpenVLA-OFT 接入 smoke 总结](../docs/stage_summaries/stage_00_oft_smoke.md)。
  关闭范围是接入与可复算 smoke；不表示完整 benchmark 验收或模型能力结论成立。

## 清理

001/002 为 accepted，尚未 closed；003 仍 open，当前无可删除文件。README、STATUS 与长期阶段总结始终保留。
每周检查；阶段完成时额外清理。只有阶段总结已推送、本地备份校验一致，才可删除已闭环交流。
