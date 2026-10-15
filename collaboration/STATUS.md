# 当前协作状态

更新：2026-10-16。当前权责以本页和[README](README.md)为准；历史记录保留，不把旧执行者署名改掉。

## 当前分工与审查方式

用户只负责确认并亲自启动真实实验；X实现代码和CPU/fake软件测试；Codex承担非实验数据／文件准备、详细需求、建议式审查、校验部署、完整启动命令及读取结果后的审查归档。Codex/X不自主启动真实仿真、数据恢复、物理标签、特征抽取、训练或模型eval。

只有明确错误、关键已约定功能缺失、真值／数据泄漏、危险控制或证据错误才阻塞；其他意见作为non-blocking建议。需求一次写完整，不因偏好反复返修。

## 当前阶段

Stage04 / [Plan4](../docs/experiment_plans/stage04_finish_protocol.md)：统一FINISH接口控制未学停止混淆。R9软件accepted后，用户3433f48特征重导出1261/1261完成（100%），Codex已逐文件验收全部cache。原audit仍复用；下一步用户启动[05_train小头训练](../docs/experiment_plans/stage04_head_training_runbook_2026-10-16.md)，不重做audit/features。当前无真实训练完成／parity／停止校准或新模型评分，008／Stage04未closed。

默认设计：冻结OFT动作网络，只训练小finish head；普通00数据分组训练／校准／独立测试，当前外部10/01/11留作测试；active与shadow分开，新协议H520/W150所有mask一致，FINISH后或超时后做真实物理保持，无GT许可停车。原始无FINISH模型仅历史参考，新主指标不把不支持写成0%。

Stage03的固定15条主pilot＋10条oracle诊断已完成；旧JSR主10=40%（2/5）、01=100%（5/5）、11=100%（5/5）；UIR未标注=N/A。指标／行为科学审查尚未closed，Plan4不改历史raw或分数。[已提交执行总结](https://github.com/No1dry/LIBERO-Remain/blob/4b5145173b979f268625bf154800f14df7194d14/docs/stage_summaries/stage_03_subset_pilot_execution.md)。

## 任务

| 任务 | 状态 | 交付／裁决 |
|---|---|---|
| [008 两来源域数据合同](tasks/008_finish_data_source_domains.md) | R9软件／真实audit／完整features accepted；待用户05_train，未closed | 3433f48重试1261/1261（100%），4096维FP32；1071train/190val，unknown52排除，全部输入hash/NPZ/label/source核验；[验收总结](../docs/stage_summaries/stage04_feature_export_pass_2026-10-16.md)／[训练命令](../docs/experiment_plans/stage04_head_training_runbook_2026-10-16.md) |
| 001 指标与人工UIR | closed | PR #1已合并；交流仍保留供后续追踪 |
| 002 venv路径修复 | closed | 同上；阶段总结与本地备份已核验 |
| 003 正常00回归入口 | accepted，PR #2已合并 | main合并SHA 4a02c78c0b945c2df2f0748614fecdd1c5127f55；不在本轮伪造closed |
| 004 runtime有效版本 | accepted，PR #3已合并 | main合并869f409；已审独立实现7318c4b；旧raw不改 |
| 005 subset pilot | accepted，PR #3已合并 | main合并869f409；已审实现7c47c12；实验冻结04508dc |
| 006 观察／试探规则 | accepted（文档），未科学闭环 | 不改001/camera/crop；旧初帧可见性闸门撤销 |
| [007 FINISH协议与停止校准](tasks/007_finish_protocol_and_stop_calibration.md) | accepted（R2软件修复），PR #4已合并，未closed | main 94c061e；[复核裁决](reviews/007_round3.md)对应4f76f49实现未改；[真实单11四步预检通过](../docs/stage_summaries/stage04_r2_preflight_pass_2026-10-14.md)，模型调用0；不等于W150或停止能力通过 |

[PR #3](https://github.com/No1dry/LIBERO-Remain/pull/3)已由Codex验收并由X于2026-10-13合并为main `869f409884b73fa7de8dcacb4c7861d6ddfa19f8`，已审实现未变；历史验收和实验冻结04508dc保留。[PR #4](https://github.com/No1dry/LIBERO-Remain/pull/4)已按007 accepted与008 A.1授权于2026-10-15合并为 `94c061e99168d76fbe50bef85b187db8fe2b9898`：已审4f76f49合入最新main规则得到48cad17，benchmark/scripts/tests/configs/pyproject均保持已验收实现。008从此main独立开分支；旧38e6a44仍仅作历史失败冻结。[合并与新实现登记](responses/008_round1.md)。

## 当前下一步

**04_features已完成并accepted，不重跑audit或features。下一步用户亲自启动05_train。** 新冻结3433f487d38efe0a08e4c814e87412aad5aba9fe的本次1261次forward全部完成，exit0/tee0；1261×4096 float32 cache已通过Codex完整load_feature_cache、1313观测／1261输入NPZ及来源／标签／角色／dtype／hash复核。cache SHA5d09999ed6b91b1927eb02bf775d623d38064fbdca12503805a34ea01bcc8efc，绑定原audit44d0ab96…和原base4601be2d…；262源码／11部署文件不变。

[训练完整命令](../docs/experiment_plans/stage04_head_training_runbook_2026-10-16.md)，[特征验收总结](../docs/stage_summaries/stage04_feature_export_pass_2026-10-16.md)，[机器回执](../docs/stage_summaries/evidence/stage04_feature_cache_acceptance_2026-10-16.json)。在现有session用finish_model 05_train train，读取新OUT/features/cache、固定REPO/configs/remaining_goals/finish/train.json、输出新OUT/train；只训小头，CPU FP32／50轮，不加载真实VLA或改动作网络。训练1071（1048负23正），验证190（188负2正），unknown52排除；验证正例仅demo_38两帧限制不改。

Codex未启动训练／新模型forward／sim。用户完成训练后再核验head并交真实parity命令，随后正常停止控制和Remain；不以缓存完成冒充stop-capable。旧2cb失败forward数仍未知，旧partial/log全保留。PR #5本轮不自动合并；X按R9已审范围保留最新main文档。008／Stage04未closed，精确待删=[]。

以下007部署与数据准备经过保留为历史，不重复已经完成的预检。

X的007需求意见此前已采纳，现已交[首轮实现与CPU/fake证据](https://github.com/No1dry/LIBERO-Remain/blob/38e6a449d4e769b842e10c5b393fc2b26a5cfa2b/collaboration/responses/007_round1.md)。Codex[软件审查accepted](reviews/007_round1.md)，无需本轮返修；已将固定源码上传新目录 `/HUBU-AI096/zp/ICML/LIBERO-Remain-stage04-finish-38e6a44`，194个源码文件及10个冻结部署文件核验一致。配置／session／新结果根为 `/HUBU-AI096/zp/ICML/stage04_finish_38e6a44`。

Codex已按用户2026-10-14委托完成固定官方basket HDF5下载与SHA核验：50条演示／14700个123维saved state／50个有效XML。纯文件检查发现50条演示均不能与现有50个official init完整精确匹配；init_state属性也只是首saved state，匹配仍0/50。当前默认来源分组不满足训练前提，file-only报告insufficient不是模型失败。详见[准备记录](../docs/stage_summaries/stage04_data_preparation_2026-10-14.md)。

用户已启动已有basket_s000_11预检；status=technical_error／command_exit=2、trace=[]、model_calls=0。固定LIBERO living-room任务使用OnTheGroundPanda，但FINISH guard只接受类名Panda，reset后的合同检查误拒绝。Codex读取当前安装源码并做CPU fake复现，已发[007_round2](reviews/007_round2.md)给X修最小兼容性错误及补回归；这是明确错误，不是效果差返修。该P1现由X修复并通过Codex[R3软件复核](reviews/007_round3.md)；旧38仍不得重跑或合并，新版本仅允许用户按下述命令做同一11物理预检，不直接进入训练。

X已交[最小修复与CPU证据](https://github.com/No1dry/LIBERO-Remain/blob/4f76f4917a9174fc5b80ef83e3cf21eaf053c98d/collaboration/responses/007_round2.md)，Codex独立复核accepted。新源码`/HUBU-AI096/zp/ICML/LIBERO-Remain-stage04-finish-4f76f49`／运行根`/HUBU-AI096/zp/ICML/stage04_finish_4f76f49`已部署，204源码和4部署文件核验，原sim/source001/replay不变。用户已完成同一source0_11的新版预检：exit0／recorded，4/4实际保持步，0..4的5/5检查时刻两目标均满足且released=True、unknown0、model_calls0。NPZ/hash和204源码/4部署文件一致，证据已本地备份。只接受这一已释放11样本的短窗口接口检查，不宣称W150、夹持负例或模型停止能力通过；不要重复运行已完成命令。HDF来源隔离仍是独立前置问题，不直接允许audit／训练／评测；不猜demo编号或伪造记录。旧模型／runtime／source_map／split／失败raw不改。

历史两个版本分开：旧38有一次技术错误，新4f有一次单11四步接口预检通过，不混成模型成功率。没有VLA forward、头训练、parity、校准或模型评测成绩；默认30条模型rollout预算未消耗。Codex只读取/校验用户产物，没有代跑或额外重试。runtime JSON逐命令SHA冻结，不阶段间改center_crop。普通停止能力、unknown覆盖与科研解释仍待真实证据，不拿软件通过当stop-capable。

[软件验收与部署长期记录](../docs/stage_summaries/stage04_software_acceptance_deployment_2026-10-13.md)提交GitHub并按README本地备份核验。旧阶段raw、视频、模型、patch与已有脏工作区保留。

## 清理与历史

Stage00接入范围closed，Stage01代码范围closed；Stage02正常00实验验收完成，但003状态仍以上表为准。Stage03仍待科学裁决，007的P1已在软件范围修复并accepted，真实预检／来源问题仍开放。用户最新规则覆盖历史计划的未来职责，不改原DeepSeek/Codex已执行记录。

001/002暂保留；其他任务非closed或仍供未合并代码追踪，均不删除。协议、STATUS、阶段总结、源码与原始数据长期保留。每周仅归档清理，不自动合并／部署／启动作业；备份来源commit和SHA一致才允许清理。本次不删除交流。

2026-10-14真实预检长期记录：[stage04_preflight_failure](../docs/stage_summaries/stage04_preflight_failure_2026-10-14.md)，GitHub与本地备份核验；失败原raw／日志保留，待删清单为空。

[R2修复验收与新部署总结](../docs/stage_summaries/stage04_r2_fix_acceptance_2026-10-14.md)已提交并本地核验；本轮没有启动真实sim/VLA/训练，待删清单仍为空。

## 数据分组修订已获用户批准

2026-10-14用户已明确选择[方案A](../docs/experiment_plans/stage04_data_domains_proposal_2026-10-14.md)：HDF整轨迹head_train/head_validation，official init另作normal_calibration/test/Remain，承认跨域物理祖源独立性未证明；不把demo编号当init、不训练编辑评测输入。Codex已更新Plan4并发[008完整新任务](tasks/008_finish_data_source_domains.md)，不是007返修。X现已合并保持已审4f实现的PR #4并从main独立交付008 PR #5；Codex不代合并。008验收部署后用户先启动audit，未充分前不训练，不新增VLA数据采集或30条eval外预算。
