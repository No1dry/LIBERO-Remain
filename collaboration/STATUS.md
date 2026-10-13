# 当前协作状态

更新：2026-10-12。当前权责以本页和[README](README.md)为准；历史记录保留，不把旧执行者署名改掉。

## 当前分工与审查方式

用户启动、运行、监督全部实验；X实现代码和CPU/fake软件测试；Codex详细需求、建议式审查、验收后上传服务器与完整可复制命令，用户交回结果后审查归档。Codex/X不启动真实仿真、数据恢复、特征抽取、训练或模型eval。

只有明确错误、关键已约定功能缺失、真值／数据泄漏、危险控制或证据错误才阻塞；其他意见作为non-blocking建议。需求一次写完整，不因偏好反复返修。

## 当前阶段

Stage04 / [Plan4](../docs/experiment_plans/stage04_finish_protocol.md)：统一FINISH接口＋普通停止校准基线，目的是明确benchmark结束点、控制未学停止的干扰，不是把基线分数做低或靠FINISH救分。007开放，尚无新实现／训练／成绩。

默认设计：冻结OFT动作网络，只训练小finish head；普通00数据分组训练／校准／独立测试，当前外部10/01/11留作测试；active与shadow分开，新协议H520/W150所有mask一致，FINISH后或超时后做真实物理保持，无GT许可停车。原始无FINISH模型仅历史参考，新主指标不把不支持写成0%。

Stage03的固定15条主pilot＋10条oracle诊断已完成；旧JSR主10=40%（2/5）、01=100%（5/5）、11=100%（5/5）；UIR未标注=N/A。指标／行为科学审查尚未closed，Plan4不改历史raw或分数。[已提交执行总结](https://github.com/No1dry/LIBERO-Remain/blob/4b5145173b979f268625bf154800f14df7194d14/docs/stage_summaries/stage_03_subset_pilot_execution.md)。

## 任务

| 任务 | 状态 | 交付／裁决 |
|---|---|---|
| 001 指标与人工UIR | closed | PR #1已合并；交流仍保留供后续追踪 |
| 002 venv路径修复 | closed | 同上；阶段总结与本地备份已核验 |
| 003 正常00回归入口 | accepted，PR #2已合并 | main合并SHA 4a02c78c0b945c2df2f0748614fecdd1c5127f55；不在本轮伪造closed |
| 004 runtime有效版本 | accepted，PR #3待合并 | 已审独立实现7318c4b；旧raw不改 |
| 005 subset pilot | accepted，PR #3待合并 | 已审实现7c47c12；实验冻结04508dc |
| 006 观察／试探规则 | accepted（文档），未科学闭环 | 不改001/camera/crop；旧初帧可见性闸门撤销 |
| [007 FINISH协议与停止校准](tasks/007_finish_protocol_and_stop_calibration.md) | open | X独立实现／CPU-fake测试；Codex部署与命令；用户实验 |

[PR #3](https://github.com/No1dry/LIBERO-Remain/pull/3)已由Codex验收（macOS1231 passed/12 skipped；Linux1243 passed），当前HEAD4b5145173b979f268625bf154800f14df7194d14，仍open。[验收记录](https://github.com/No1dry/LIBERO-Remain/blob/a3376c26576789d36ee11c39b2abe6e09e74cbe0/collaboration/reviews/005_round1.md)。X按既有授权合并登记；Codex不代合并。007从包含该实现和最新规则的main开新分支，不追加进PR #3。新增未审实现仍需独立检查。

## 当前下一步

X已完成[007需求审阅](responses/007_scope_review_20261013.md)：整体赞同Plan4，集中登记停止能力假通过、来源映射、safe hold和新协议证据等实现边界；这不是007代码交付，本轮未实现、合并或启动实验，任务仍open。

X读取007与Plan4，交独立PR、实际CPU/fake结果、入口／dry-plan和完整候选runbook。Codex审查后上传冻结版本并补齐机器路径／SHA，用户逐步启动。阶段能力检查不自动变成代码返修。

本轮角色交接和协议决策长期记录于[2026-10-12总结](../docs/stage_summaries/handoff_2026-10-12_finish_protocol.md)，本地同步备份。旧正常00与Stage03证据、模型、runtime和状态不覆盖；无新实验在本轮被启动。

## 清理与历史

Stage00接入范围closed，Stage01代码范围closed；Stage02正常00实验验收完成，但003状态仍以上表为准。Stage03仍待科学裁决，007新阶段开放。用户最新规则覆盖历史计划的未来职责，不改原DeepSeek/Codex已执行记录。

001/002暂保留；其他任务非closed或仍供未合并代码追踪，均不删除。协议、STATUS、阶段总结、源码与原始数据长期保留。每周仅归档清理，不自动合并／部署／启动作业；备份来源commit和SHA一致才允许清理。本次不删除交流。
