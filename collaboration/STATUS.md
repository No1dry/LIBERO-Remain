# 当前协作状态

更新：2026-10-09（Codex 验收任务003）。代码：X；代码与实验审查：Codex；实验执行：DeepSeek。

## 当前大阶段

Stage 02：提供单任务、多初态的官方 / Remain normal-00 能力回归入口。
阶段状态：任务003代码 accepted，待X合并PR #2并登记main SHA。之后授权DeepSeek按执行说明先2条技术smoke，再固定10条00回归。

Stage01 closed：PR #1已合并，Codex已核验main与既有归档一致；最终关闭总结同步更新。

| 任务 | 执行者 | 状态 | 入口 | 交付/裁决 |
|---|---|---|---|---|
| 001 指标展示与人工 UIR | X | closed | [任务](tasks/001_metrics_and_uir.md) | PR #1已合并；功能验收完成 |
| 002 venv 解释器路径修复 | X | closed | [任务](tasks/002_venv_interpreter.md) | 同上；阶段总结/本地归档已核验 |
| 003 官方/Remain 00 回归入口 | X | accepted | [任务](tasks/003_normal00_regression_entry.md) | [PR #2](https://github.com/No1dry/LIBERO-Remain/pull/2)、[回应](responses/003_round1.md)、[Codex review](reviews/003_round1.md) |

Stage 01 main 合并 SHA：`fea75fc170b5c3047433316566dc52528c5caf2a`，见[合并登记](responses/stage01_merge_record.md)。
此前 Codex 独立 macOS 985 passed / 12 skipped、Linux 986 passed / 11 skipped，历史 OFT 数据只读派生与旧分数不变已核验。
X 按明确验收授权合并，未自行宣告阶段 closed。

任务 003 实现提交 `3a50f635b5eb7329386b381879ce53dab3bfbd46`。
X测试1092 passed/15 skipped；Codex独立macOS1095 passed/12 skipped、Linux1096 passed/11 skipped。
两个无模型的真实环境检查通过：official准确初态/10wait；Remain80settle/150audit/正式恢复逐位一致。
没有新VLA分数；后续模型回归不冒充完整paired benchmark。

Stage01的[关闭总结](../docs/stage_summaries/stage_01_metrics_uir.md)与本地备份同步更新。
下一步X合并PR #2，DeepSeek按[实验说明](../docs/experiment_plans/stage02_normal00_first_batch.md)机械执行。
既有四视频的人工UIR语义校准仍由Codex/用户负责。

## 已关闭阶段

- Stage 00：[首次真实 OpenVLA-OFT 接入 smoke 总结](../docs/stage_summaries/stage_00_oft_smoke.md)。
  关闭范围是接入与可复算 smoke；不表示完整 benchmark 验收或模型能力结论成立。

## 清理

001/002已closed，本轮仍保留交流供当前PR追踪；003仅accepted，不清理。README、STATUS与阶段总结长期保留。
每周检查；阶段完成时额外清理。只有阶段总结已推送、本地备份校验一致，才可删除已闭环交流。
