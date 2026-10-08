# 当前协作状态

更新：2026-10-08（X 提交实现待审）。代码：X；代码与实验审查：Codex；实验执行：DeepSeek。

## 当前大阶段

Stage 01：精简指标展示、建立人工 UIR 标注与汇总，并集成已验证的 venv 解释器修复。
阶段状态：open。尚未验收，暂不启动新的正式 GPU 评测。

| 任务 | 执行者 | 状态 | 入口 | 交付/裁决 |
|---|---|---|---|---|
| 001 指标展示与人工 UIR | X | submitted | [任务](tasks/001_metrics_and_uir.md) | [PR #1](https://github.com/No1dry/LIBERO-Remain/pull/1)、[回应](responses/001_round1.md)；待 Codex review |
| 002 venv 解释器路径修复 | X | submitted | [任务](tasks/002_venv_interpreter.md) | 同一 [PR #1](https://github.com/No1dry/LIBERO-Remain/pull/1)、[回应](responses/002_round1.md)；待 Codex review |

实现提交 `46d935b1b8e8109bbc840a2e4347ed520cdd4df7`，分支 `x/stage01-metrics-uir-venv`。
最终本机回归 982 passed / 15 skipped；限制及 CPU synthetic 证据见回应。尚未合并，X 不给出 accepted/closed 裁决。

001/002 可独立编码；Stage 01 验收要求两项都闭环。完成代码验收后，Codex 再给 DeepSeek 实验命令。

## 已关闭阶段

- Stage 00：[首次真实 OpenVLA-OFT 接入 smoke 总结](../docs/stage_summaries/stage_00_oft_smoke.md)。
  关闭范围是接入与可复算 smoke；不表示完整 benchmark 验收或模型能力结论成立。

## 清理

当前交流均为开放任务，无可删除文件。README、STATUS 与长期阶段总结始终保留。
每周检查；阶段完成时额外清理。只有阶段总结已推送、本地备份校验一致，才可删除已闭环交流。
