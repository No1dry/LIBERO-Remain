# 当前协作状态

更新：2026-10-07。代码：X；代码与实验审查：Codex；实验执行：DeepSeek。

## 当前大阶段

Stage 01：精简指标展示、建立人工 UIR 标注与汇总，并集成已验证的 venv 解释器修复。
阶段状态：open。尚未验收，暂不启动新的正式 GPU 评测。

| 任务 | 执行者 | 状态 | 入口 | 交付/裁决 |
|---|---|---|---|---|
| 001 指标展示与人工 UIR | X | open | [任务](tasks/001_metrics_and_uir.md) | 待代码提交、PR 与 response |
| 002 venv 解释器路径修复 | X | open | [任务](tasks/002_venv_interpreter.md) | 有经过 smoke 验证的参考补丁；待正式集成 |

001/002 可独立编码；Stage 01 验收要求两项都闭环。完成代码验收后，Codex 再给 DeepSeek 实验命令。

## 已关闭阶段

- Stage 00：[首次真实 OpenVLA-OFT 接入 smoke 总结](../docs/stage_summaries/stage_00_oft_smoke.md)。
  关闭范围是接入与可复算 smoke；不表示完整 benchmark 验收或模型能力结论成立。

## 清理

当前交流均为开放任务，无可删除文件。README、STATUS 与长期阶段总结始终保留。
每周检查；阶段完成时额外清理。只有阶段总结已推送、本地备份校验一致，才可删除已闭环交流。
