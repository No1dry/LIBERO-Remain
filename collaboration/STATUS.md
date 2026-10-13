# 当前协作状态

更新：2026-10-13。当前权责以本页和[README](README.md)为准；历史记录保留，不把旧执行者署名改掉。

## 当前分工与审查方式

用户启动、运行、监督全部实验；X实现代码和CPU/fake软件测试；Codex详细需求、建议式审查、验收后上传服务器与完整可复制命令，用户交回结果后审查归档。Codex/X不启动真实仿真、数据恢复、特征抽取、训练或模型eval。

只有明确错误、关键已约定功能缺失、真值／数据泄漏、危险控制或证据错误才阻塞；其他意见作为non-blocking建议。需求一次写完整，不因偏好反复返修。

## 当前阶段

Stage04 / [Plan4](../docs/experiment_plans/stage04_finish_protocol.md)：统一FINISH接口＋普通停止校准基线，目的是明确benchmark结束点、控制未学停止的干扰，不是把基线分数做低或靠FINISH救分。007已由Codex软件验收accepted并部署冻结38e6a44；真实训练／实验尚未启动，Stage04未closed。

默认设计：冻结OFT动作网络，只训练小finish head；普通00数据分组训练／校准／独立测试，当前外部10/01/11留作测试；active与shadow分开，新协议H520/W150所有mask一致，FINISH后或超时后做真实物理保持，无GT许可停车。原始无FINISH模型仅历史参考，新主指标不把不支持写成0%。

Stage03的固定15条主pilot＋10条oracle诊断已完成；旧JSR主10=40%（2/5）、01=100%（5/5）、11=100%（5/5）；UIR未标注=N/A。指标／行为科学审查尚未closed，Plan4不改历史raw或分数。[已提交执行总结](https://github.com/No1dry/LIBERO-Remain/blob/4b5145173b979f268625bf154800f14df7194d14/docs/stage_summaries/stage_03_subset_pilot_execution.md)。

## 任务

| 任务 | 状态 | 交付／裁决 |
|---|---|---|
| 001 指标与人工UIR | closed | PR #1已合并；交流仍保留供后续追踪 |
| 002 venv路径修复 | closed | 同上；阶段总结与本地备份已核验 |
| 003 正常00回归入口 | accepted，PR #2已合并 | main合并SHA 4a02c78c0b945c2df2f0748614fecdd1c5127f55；不在本轮伪造closed |
| 004 runtime有效版本 | accepted，PR #3已合并 | main合并869f409；已审独立实现7318c4b；旧raw不改 |
| 005 subset pilot | accepted，PR #3已合并 | main合并869f409；已审实现7c47c12；实验冻结04508dc |
| 006 观察／试探规则 | accepted（文档），未科学闭环 | 不改001/camera/crop；旧初帧可见性闸门撤销 |
| [007 FINISH协议与停止校准](tasks/007_finish_protocol_and_stop_calibration.md) | accepted（软件），PR #4未合并，未closed | [审查裁决](reviews/007_round1.md)；冻结38e6a44；本地1468 passed/12 skipped，新237；服务器新237；用户真实阶段待运行 |

[PR #3](https://github.com/No1dry/LIBERO-Remain/pull/3)已由Codex验收并由X于2026-10-13合并为main `869f409884b73fa7de8dcacb4c7861d6ddfa19f8`，已审实现未变；历史验收和实验冻结04508dc保留。007为独立[PR #4](https://github.com/No1dry/LIBERO-Remain/pull/4)，已审head `38e6a449d4e769b842e10c5b393fc2b26a5cfa2b`；仅文档不同于X测试实现55474fd。Codex本次不合并实现，X按既有授权保留已审实现并登记merge。

## 当前下一步

X的007需求意见此前已采纳，现已交[首轮实现与CPU/fake证据](https://github.com/No1dry/LIBERO-Remain/blob/38e6a449d4e769b842e10c5b393fc2b26a5cfa2b/collaboration/responses/007_round1.md)。Codex[软件审查accepted](reviews/007_round1.md)，无需本轮返修；已将固定源码上传新目录 `/HUBU-AI096/zp/ICML/LIBERO-Remain-stage04-finish-38e6a44`，194个源码文件及10个冻结部署文件核验一致。配置／session／新结果根为 `/HUBU-AI096/zp/ICML/stage04_finish_38e6a44`。

用户按[完整服务器命令](../docs/experiment_plans/stage04_server_runbook_2026-10-13.md)，先运行basket_s000_11真实4步hold／release预检，再自行补齐官方basket HDF5和来源audit，交回报告。现有init/BDDL/source001/replay/模型/runtime已核；旧datasets目录空，核对范围未找到该HDF5。数据映射不足要保存insufficient，不猜demo编号；不是软件返修门槛。

本次没有真实仿真／restore／feature／头训练／parity／校准／eval。默认30rollout预算尚未消耗；之后由用户逐阶段启动并交Codex审查。runtime JSON逐命令SHA冻结，不阶段间改center_crop。普通停止能力、unknown覆盖与科研解释仍待真实证据，不拿软件通过当stop-capable。

[软件验收与部署长期记录](../docs/stage_summaries/stage04_software_acceptance_deployment_2026-10-13.md)提交GitHub并按README本地备份核验。旧阶段raw、视频、模型、patch与已有脏工作区保留。

## 清理与历史

Stage00接入范围closed，Stage01代码范围closed；Stage02正常00实验验收完成，但003状态仍以上表为准。Stage03仍待科学裁决，007新阶段开放。用户最新规则覆盖历史计划的未来职责，不改原DeepSeek/Codex已执行记录。

001/002暂保留；其他任务非closed或仍供未合并代码追踪，均不删除。协议、STATUS、阶段总结、源码与原始数据长期保留。每周仅归档清理，不自动合并／部署／启动作业；备份来源commit和SHA一致才允许清理。本次不删除交流。
