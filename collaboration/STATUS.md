# 当前协作状态

更新：2026-10-14。当前权责以本页和[README](README.md)为准；历史记录保留，不把旧执行者署名改掉。

## 当前分工与审查方式

用户只负责确认并亲自启动真实实验；X实现代码和CPU/fake软件测试；Codex承担非实验数据／文件准备、详细需求、建议式审查、校验部署、完整启动命令及读取结果后的审查归档。Codex/X不自主启动真实仿真、数据恢复、物理标签、特征抽取、训练或模型eval。

只有明确错误、关键已约定功能缺失、真值／数据泄漏、危险控制或证据错误才阻塞；其他意见作为non-blocking建议。需求一次写完整，不因偏好反复返修。

## 当前阶段

Stage04 / [Plan4](../docs/experiment_plans/stage04_finish_protocol.md)：统一FINISH接口＋普通停止校准基线，目的是明确benchmark结束点、控制未学停止的干扰，不是把基线分数做低或靠FINISH救分。007已部署冻结38e6a44；用户首次真实11预检因机器人类型检查技术错误失败，现changes_requested（单个P1兼容性问题）。X已提交修复a7dda8d与CPU证据，待Codex复核，尚未部署或重跑真实预检。没有新模型成绩，Stage04未closed。

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
| [007 FINISH协议与停止校准](tasks/007_finish_protocol_and_stop_calibration.md) | changes_requested；X已交修复，待R2复核；PR #4未合并，未closed | [真实预检审查](reviews/007_round2.md)／[X修复交付](responses/007_round2.md)；实现a7dda8d支持固定OnTheGroundPanda；保留R1及旧失败证据 |

[PR #3](https://github.com/No1dry/LIBERO-Remain/pull/3)已由Codex验收并由X于2026-10-13合并为main `869f409884b73fa7de8dcacb4c7861d6ddfa19f8`，已审实现未变；历史验收和实验冻结04508dc保留。007为独立[PR #4](https://github.com/No1dry/LIBERO-Remain/pull/4)，已审head `38e6a449d4e769b842e10c5b393fc2b26a5cfa2b`；仅文档不同于X测试实现55474fd。Codex本次不合并实现，X按既有授权保留已审实现并登记merge。

## 当前下一步

X已交[第二轮最小修复与CPU证据](responses/007_round2.md)，实现SHA `a7dda8d28e35c93aa8eead675075b113612f7d15`；精确接受官方Panda与OnTheGroundPanda完整类身份，原夹爪／OSC和FINISH语义不变。新增24项回归；10个FINISH测试文件261 passed／0 skipped，全套1489 passed／15个既有skip。当前等待Codex复核，不自行accepted、合并或启动真实实验；最终交付head见PR #4正文。

历史：X的007需求意见此前已采纳，已交[首轮实现与CPU/fake证据](https://github.com/No1dry/LIBERO-Remain/blob/38e6a449d4e769b842e10c5b393fc2b26a5cfa2b/collaboration/responses/007_round1.md)。Codex的[R1软件审查accepted](reviews/007_round1.md)记录保留，当前以R2新证据和裁决为准。旧固定源码位于 `/HUBU-AI096/zp/ICML/LIBERO-Remain-stage04-finish-38e6a44`，194个源码文件及10个冻结部署文件核验一致。旧配置／session／结果根为 `/HUBU-AI096/zp/ICML/stage04_finish_38e6a44`。

Codex已按用户2026-10-14委托完成固定官方basket HDF5下载与SHA核验：50条演示／14700个123维saved state／50个有效XML。纯文件检查发现50条演示均不能与现有50个official init完整精确匹配；init_state属性也只是首saved state，匹配仍0/50。当前默认来源分组不满足训练前提，file-only报告insufficient不是模型失败。详见[准备记录](../docs/stage_summaries/stage04_data_preparation_2026-10-14.md)。

用户已启动已有basket_s000_11预检；status=technical_error／command_exit=2、trace=[]、model_calls=0。固定LIBERO living-room任务使用OnTheGroundPanda，但FINISH guard只接受类名Panda，reset后的合同检查误拒绝。Codex读取当前安装源码并做CPU fake复现，已发[007_round2](reviews/007_round2.md)给X修最小兼容性错误及补回归；这是明确错误，不是效果差返修。当前暂停全部受影响真实FINISH阶段，不让用户重跑原命令，不合并未修38版。

X已交新SHA／CPU测试；Codex复核验收后部署新目录和命令，用户再启动同一source0_11的4步预检。HDF来源隔离仍是独立前置问题，兼容性修复不自动允许audit／训练／评测；不猜demo编号或伪造记录。runtime/source_map/split/旧原始结果未变。

用户已有一次真实预检启动，失败在reset后合同检查，没有4步hold trace、VLA forward、训练、parity、校准或评测成绩。默认30条模型rollout预算尚未消耗；Codex只读审查／CPU fake，没有代跑或重试。runtime JSON逐命令SHA冻结，不阶段间改center_crop。普通停止能力、unknown覆盖与科研解释仍待真实证据，不拿软件通过当stop-capable。

[软件验收与部署长期记录](../docs/stage_summaries/stage04_software_acceptance_deployment_2026-10-13.md)提交GitHub并按README本地备份核验。旧阶段raw、视频、模型、patch与已有脏工作区保留。

## 清理与历史

Stage00接入范围closed，Stage01代码范围closed；Stage02正常00实验验收完成，但003状态仍以上表为准。Stage03仍待科学裁决，007有未解决P1审查，新阶段开放。用户最新规则覆盖历史计划的未来职责，不改原DeepSeek/Codex已执行记录。

001/002暂保留；其他任务非closed或仍供未合并代码追踪，均不删除。协议、STATUS、阶段总结、源码与原始数据长期保留。每周仅归档清理，不自动合并／部署／启动作业；备份来源commit和SHA一致才允许清理。本次不删除交流。

2026-10-14真实预检长期记录：[stage04_preflight_failure](../docs/stage_summaries/stage04_preflight_failure_2026-10-14.md)，GitHub与本地备份核验；失败原raw／日志保留，待删清单为空。
