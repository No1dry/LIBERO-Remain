# 当前协作状态

更新：2026-10-09（用户确认执行职责移交并推进实验）。代码：X；研究决策、代码审查、实验执行与结果审查：Codex。后续不再使用 DeepSeek。

## 当前大阶段

Stage 02：提供单任务、多初态的官方 / Remain normal-00 能力回归入口。
阶段状态：任务003代码 accepted；PR #2 尚未合并，main 仍为 Stage01 版本。用户确认推进实验后，Codex 可使用独立目录中冻结的已审查提交 `6e29f110b56a18ade63f401a1b6d8376fa9f95ba`，先2条技术smoke，再固定10条00回归。X 仍负责合并和登记 main SHA；不得把 PR 版本称作已合并 main。

Stage01 closed：PR #1已合并，Codex已核验main与既有归档一致；最终关闭总结同步更新。

| 任务 | 执行者 | 状态 | 入口 | 交付/裁决 |
|---|---|---|---|---|
| 001 指标展示与人工 UIR | X | closed | [任务](tasks/001_metrics_and_uir.md) | PR #1已合并；功能验收完成 |
| 002 venv 解释器路径修复 | X | closed | [任务](tasks/002_venv_interpreter.md) | 同上；阶段总结/本地归档已核验 |
| 003 官方/Remain 00 回归入口 | X | accepted | [任务](tasks/003_normal00_regression_entry.md) | [PR #2](https://github.com/No1dry/LIBERO-Remain/pull/2)、[回应](responses/003_round1.md)、[Codex review](reviews/003_round1.md) |
| 004 layered环境有效版本记录 | X | open | [任务](tasks/004_effective_runtime_provenance.md) | P2元数据；不改当前冻结实验 |

Stage 01 main 合并 SHA：`fea75fc170b5c3047433316566dc52528c5caf2a`，见[合并登记](responses/stage01_merge_record.md)。
此前 Codex 独立 macOS 985 passed / 12 skipped、Linux 986 passed / 11 skipped，历史 OFT 数据只读派生与旧分数不变已核验。
X 按明确验收授权合并，未自行宣告阶段 closed。

任务 003 实现提交 `3a50f635b5eb7329386b381879ce53dab3bfbd46`。
X测试1092 passed/15 skipped；Codex独立macOS1095 passed/12 skipped、Linux1096 passed/11 skipped。
两个无模型的真实环境检查通过：official准确初态/10wait；Remain80settle/150audit/正式恢复逐位一致。
代码验收时没有新VLA分数；后续模型回归不冒充完整paired benchmark。

Stage01的[关闭总结](../docs/stage_summaries/stage_01_metrics_uir.md)与本地备份同步更新。
下一步Codex按[实验说明](../docs/experiment_plans/stage02_normal00_first_batch.md)执行，X完成PR #2合并登记。冻结后不随分支更新；任何新增实现须重新审查。
交接盘点见[交接记录](../docs/stage_summaries/handoff_2026-10-09.md)：已知服务器目录未发现正在运行的本阶段作业或新的正式00回归结果；此前只有旧smoke与无模型预检。运行进度以新 `execute_logs/stage02_normal00/` 和原始run记录为准。
用户随后指定新主机端口30369与 `/HUBU-AI096/zp/ICML`。实际是A100 80GB；初始空目录已建立冻结checkout和两套私有runtime，同一checkpoint的112个文件全部SHA-256校验通过，固定LIBERO1029个Git blobs与真实scene doctor通过。旧OFT tracked patch hash也一致。新机Python3.10.21，旧机3.10.20；simulation torch复用2.4.1+cu121而非旧CPU2.2.0，关键MuJoCo/robosuite版本保持并记录差异。
index0两条技术smoke已于10:43:23 UTC完成，独立闸门passed：official253步成功，Remain670步成功，视频解码254/671帧；smoke不进入正式分母。正式固定5+5于10:47:15 UTC启动，wrapper PID3655463，`reports/normal00_formal_001` 与 `execute_logs/stage02_normal00/` 保存进度，完成后停止扩展并审查。旧4090未启动本批GPU作业。
新发现worker版本dict错误选择parent的shadowed distribution，已给X任务004。独立有效版本快照与episode.runtime确认实际加载版本正确；当前批原始记录不重写，报告此警告，不借修复换模型/协议。
既有四视频的人工UIR语义校准仍由Codex/用户负责。

## 已关闭阶段

- Stage 00：[首次真实 OpenVLA-OFT 接入 smoke 总结](../docs/stage_summaries/stage_00_oft_smoke.md)。
  关闭范围是接入与可复算 smoke；不表示完整 benchmark 验收或模型能力结论成立。

## 清理

001/002已closed，本轮仍保留交流供当前PR追踪；003仅accepted，不清理。README、STATUS与阶段总结长期保留。
每周检查；阶段完成时额外清理。只有阶段总结已推送、本地备份校验一致，才可删除已闭环交流。
