# Codex：008 Round 3——provider最小修复软件验收

日期：2026-10-15。裁决：**accepted（R2软件修复），008及Stage04未closed**。本轮无进一步返修要求；不追加独立预检、重新下载或新采集。

[PR #5](https://github.com/No1dry/LIBERO-Remain/pull/5)已测试实现 `31a8d6bbf01921a9414ede5740e354730c4c5471`，最终冻结 `9ddd40f2968ed5dc3d0e0be59db00b8e91d28e5c`，tree `43560310456a0aeb90288f5bdb00090345e82605`。测试实现到最终交付只有STATUS与R2 response文档。X保留最新main19f5cec的R1验收、R2故障及协作规则。

## 明确P1已在软件范围解决

- provider构造reset后及_model XML reset后，不再在夹爪目标同步前构造BasketContract。
- 每个model选择/帧恢复先失效旧合同，restore_raw_state成功后才严格验证并绑定本帧；未恢复成功不能读truth/hold。
- hold分支finally先恢复父XML/state、验证精确state，再重新绑定合同；失败不留旧合同冒充有效。
- _robot_contract shape(2,)、finite/range、两类robot、Panda/OSC、现有hold/release均未放宽；没有补零/format_action或额外物理step/开闭爪。
- 唯一生产文件environment.py，19增7删，全部在DemonstrationAuditProvider类内；Codex实际AST核对该类以外未变，其余benchmark/scripts/configs生产文件逐字节与b596一致。原标签、分组、网络/优化器、阈值和指标未改。

新增回归经过生产DemonstrationAuditProvider/BasketContract/PandaPoseHold，而不是只测绕开的FakeProvider。覆盖native/XML reset一维占位→恢复后两指同步、连续帧/父状态重绑、非法目标拒绝、tinyHDF正负标签与异常partial/关闭。既有真实失败仍是0个采样帧，不被改写为标签或科研分数。

## Codex独立测试

| 范围 | 实际结果 |
|---|---|
| 本地新增provider两文件 | 21 passed / 0 skipped，0.63秒 |
| 本地全套 | 1645 passed / 12 skipped，50.20秒，共1657项 |
| 并行独立provider/environment/data-domains | 115 passed / 0 skipped，3.08秒 |

12个skip均为既有可选项：11个缺固定模拟器源码的catalog检查、1个缺imageio_ffmpeg；无新增008 skip。与X Windows的1642/15平台差异不矛盾。

本地JUnit：cpu_provider.xml SHA `92445460196559c34f8f40b3ad9a1e9f7e8bb9f321a7318c86e0e09c38d9dde5`；cpu_full.xml SHA `d26d3db86e28f12feacf59e5aa31be3a4fbbd4abcd7c5898166550b3c8a6759b`，均在项目reports/stage04_task008_r2_fix_2026-10-15/。

## 范围与交接

228个源码文件已逐Git blob/SHA核验，部署到全新目录并保留b596失败。[部署与服务器证据](../../docs/stage_summaries/stage04_task008_r2_fix_acceptance_2026-10-15.md)，[新会话与实际命令](../../docs/experiment_plans/stage04_task008_r2_server_runbook_2026-10-15.md)。

**真实audit仍待用户重跑，不声称真实可用标签已通过。** 软件fake不证明真实物理正确性/类别充分或停止能力；HDF/eval物理祖源仍unproven。Codex本轮没有启动真实仿真、状态恢复、label、VLA、特征、训练或eval。

解除本P1的合并暂停：X可保留最新README/Plan4/STATUS、R1/R2/R3及原始证据，保持已审实现不变，合并PR #5并登记merge SHA；Codex不代合并。不等合并才运行已冻结版本。

下一步：用户用新9ddd40f会话仅重跑同一1313帧audit；Codex读取完整性/0/1/unknown/身份，数据充分后直接给feature和训练命令。没有独立11预检、额外下载或新rollout要求。007/008及研究阶段未closed，精确待删清单=[]，不删除交流或实验产物。
