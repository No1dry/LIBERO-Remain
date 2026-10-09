# Stage02总结：正常00能力前提已完成，主实验转向10/01/11

日期：2026-10-09。作者/执行/审查：Codex。实验范围已验收完成；003代码accepted，PR #2 main合并登记仍待X，不把未合并代码称作main。004版本记录修复开放，不删除其交流。
本总结不是Plan2全部完结或完整benchmark发布，也不是模型已经学会“不行动”的结论。

## 目标与冻结身份

旧单例00失败使partial失败解释缺少能力前提。本阶段只验证同checkpoint、同basket任务的5个固定官方来源初态，在official与Remain协议上是否正常完成。
冻结benchmark HEAD `6e29f110b56a18ade63f401a1b6d8376fa9f95ba`，实现 `3a50f635b5eb7329386b381879ce53dab3bfbd46`，实验时无benchmark/scripts/tests/configs未审变更。
同一官方SOG10 OFT checkpoint，snapshot `638918f3d1c2e43a39a8a20772bdb8b91835e4b7`；从旧4090迁移到A100 80GB，整个checkpoint目录112文件SHA-256一致。此证明迁移一致，不宣称旧目录所有代码/配置都是干净官方字节。
OFT HEAD e4287，旧tracked patch SHA-256 `9398a8735f4ddeb942a966e49b170f6c0e09d5bdf75011304aa42eec7e7876d1` 保留并一致。
固定LIBERO8f1084，源码1029个Git blobs通过；simulation robosuite1.4.0/MuJoCo2.3.7/numpy1.26.4，native model robosuite1.4.1/MuJoCo2.3.7/numpy1.24.4，torch2.4.1+cu121。两Python3.10.21；硬件/补丁版本及simulation torch与旧机有差异。
policy seed7、8-action chunk、center_crop；每case隔离重置seed，不声称CUDA逐位确定性，也不冒充官方多episode一次seed的随机流。

## 执行与结果

先index0两条技术smoke，228.39s/exit0；独立检查通过。它们不进入正式分母。
正式indices0..4×official/remain共10条，于北京时间18:47:15–19:03:44运行，988.71s/exit0。
expected/attempted/completed均10；准备/加载/运行错误0，missing0，双相机完整MP4共10个。

| 协议 | 预算内全部目标成功 | 原生成功 | 最终保持/JSR | 完整条数 |
|---|---|---|---|---|
| official | 5/5 | 5/5，成功即评估器停止 | 不适用，未执行Remain保持合同 | 5/5 |
| Remain | 5/5 | 5/5 | stable5/5，joint5/5 | 5/5 |

| 来源index | official成功步 | Remain首次成功步 | Remain总策略步 |
|---|---:|---:|---:|
| 0 | 253 | 279 | 670 |
| 1 | 271 | 231 | 670 |
| 2 | 304 | 249 | 670 |
| 3 | 249 | 270 | 670 |
| 4 | 269 | 289 | 670 |

00没有初始已完成目标，preservation=null，joint在此退化为stable，不将几个重复分数包装成独立证据。
Remain各条首次全部成功后目标没有再变false，但仍平均执行406.4策略步；不据动作步数/闭爪次数自动标注不必要干预。UIR未标注=N/A，非0%。official结束来自评估器，非模型主动STOP。

## 独立复核和原始证据

逐case raw与run记录一致；固定indices和expected5+5、step0=00、连续trace、首动作、norm key、H520/等待/Remain准备80+150/完整670预算通过。
summary独立复算一致，Remain原metrics逐条从trace重算一致；step0 NPZ哈希/结构检查通过；10段MP4实际解码帧数等于n_steps+1。冻结代码未改。
已知 `policy_worker.provenance()` 汇总所有可见distribution后排序dict会误报parent shadowed版本。实际case.runtime、独立import模块版本/路径及有效metadata一致；补充effective_runtime_versions.json，raw不改。X任务004处理此可复现性字段，不影响已确认的执行与计分。

服务器原始输出：`/HUBU-AI096/zp/ICML/LIBERO-Remain-normal00-stage02/reports/normal00_formal_001/`。
本地完整证据：`reports/server_handoff_2026-10-09/normal00_formal_001/`，连同原smoke、112文件SHA清单、doctor、技术gate、有效版本快照等保留在同级目录。
关键本地文件SHA-256：

- run.json：`e06feb54a4623c15ca69f69c15ea66420eb0b6171114b73a30185e8b47eff946`。
- summary.json：`88c78986c4b32445eca05379096d60c91bd9f2537d507497a8a5c45a82f4a141`。
- plan.json：`aca90111937a8596f744896977b4d63f47b4e99e8c6411b0ca09ff33b0d1f00e`。

## 科学裁决与下一阶段

支持：这5个正常来源初态下，本checkpoint具有完成basket原任务的能力；两个协议这次均通过00能力回归。
不支持：旧00失败只是偶然/只是硬件原因；两个协议完全相同；模型会正确跳过任意外部完成目标；模型已经学会停止；一般VLA缺少目标重判能力。
小样本同任务固定seed，不作为泛化或显著性结论；旧单例与本批硬件/协议/随机流等差异不单因素归因。

用户重新明确主问题为外部任意子集提前完成后的剩余目标选择与已有成果保留。00作为能力对照到此结束，后续按[Plan3](../experiment_plans/stage03_subset_pilot.md)评价10/01/11，主表只JSR/UIR。
下一阶段先准备5组完整四mask状态与独立回放，再做可见/语义/剩余执行证据审查；X任务005补显式执行选择与隔离oracle指令诊断，Codex验收后执行固定15条主pilot。GT只可用于评估/显式诊断，不能替主模型停车或提供剩余提示。

## 交流与备份

相关：tasks/003_normal00_regression_entry.md、responses/003_round1.md、reviews/003_round1.md、首批执行计划、handoff_2026-10-09.md；004仍开放，005为下一阶段开放任务。
总结发布后复制到本地research_archive/LIBERO-Remain/stage_summaries/并在backup_manifest.json登记来源commit/SHA-256，核对远端/本地一致。
本轮不删除交流或原始资产。003待main合并登记，004/005开放，不能把这些文件按已闭环清理。
