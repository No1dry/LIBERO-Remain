# 当前协作状态

更新：2026-10-09（X 合并已验收的 PR #1，提交任务 003）。代码：X；代码与实验审查：Codex；实验执行：DeepSeek。

## 当前大阶段

Stage 02：提供单任务、多初态的官方 / Remain normal-00 能力回归入口。
阶段状态：任务 003 submitted，等待 Codex review。暂不启动新的 GPU 评测。

Stage 01 保持 accepted；PR #1 已合并，closed 仍待 Codex 对 main 与归档备份核验。

| 任务 | 执行者 | 状态 | 入口 | 交付/裁决 |
|---|---|---|---|---|
| 001 指标展示与人工 UIR | X | accepted | [任务](tasks/001_metrics_and_uir.md) | [PR #1](https://github.com/No1dry/LIBERO-Remain/pull/1)、[回应](responses/001_round1.md)、[Codex review](reviews/stage01_round1.md) |
| 002 venv 解释器路径修复 | X | accepted | [任务](tasks/002_venv_interpreter.md) | 同一 PR；[回应](responses/002_round1.md)、[Codex review](reviews/stage01_round1.md) |
| 003 官方/Remain 00 回归入口 | X | submitted | [任务](tasks/003_normal00_regression_entry.md) | [回应](responses/003_round1.md)；独立分支 `x/task003-normal00-regression`，待 Codex 审查 |

Stage 01 main 合并 SHA：`fea75fc170b5c3047433316566dc52528c5caf2a`，见[合并登记](responses/stage01_merge_record.md)。
此前 Codex 独立 macOS 985 passed / 12 skipped、Linux 986 passed / 11 skipped，历史 OFT 数据只读派生与旧分数不变已核验。
X 按明确验收授权合并，未自行宣告阶段 closed。

任务 003 实现提交 `3a50f635b5eb7329386b381879ce53dab3bfbd46`。
X 全套 CPU/fake 测试 1092 passed / 15 skipped；dry-run 恰为 basket 0..4 的 5 official + 5 remain。
未运行真实仿真或 GPU；官方模型分数尚未验证。新回归不冒充完整 paired benchmark。

Stage 01 的[总结](../docs/stage_summaries/stage_01_metrics_uir.md)已写并本地归档；最终版本与备份一致性待 Codex 核验。
下一步先对旧四视频做人工 UIR 校准，再审任务 003；DeepSeek 只做模板/报告操作及之后的固定 00 回归。

## 已关闭阶段

- Stage 00：[首次真实 OpenVLA-OFT 接入 smoke 总结](../docs/stage_summaries/stage_00_oft_smoke.md)。
  关闭范围是接入与可复算 smoke；不表示完整 benchmark 验收或模型能力结论成立。

## 清理

001/002 为 accepted，尚未 closed；003 为 submitted，当前无可删除文件。README、STATUS 与长期阶段总结始终保留。
每周检查；阶段完成时额外清理。只有阶段总结已推送、本地备份校验一致，才可删除已闭环交流。
