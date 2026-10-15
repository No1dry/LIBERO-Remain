# Stage04：008 R2初始化顺序修复验收与新部署

2026-10-15。[R3软件裁决](../../collaboration/reviews/008_round3.md)：accepted，无进一步返修；008和Stage04未closed。用户启动真实阶段，X改代码，Codex做CPU/fake审查、文件准备与部署。

## 已完成及身份

[PR #5](https://github.com/No1dry/LIBERO-Remain/pull/5)已测试实现31a8d6bbf01921a9414ede5740e354730c4c5471；最终冻结9ddd40f2968ed5dc3d0e0be59db00b8e91d28e5c，tree43560310456a0aeb90288f5bdb00090345e82605；测试实现到head只有STATUS/R2回应。最新main19f5cec的故障记录和协议保留。

唯一生产diff：environment.py中DemonstrationAuditProvider，19增7删。删除native/XML reset后两处同步前合同构造，逐帧清空旧合同、真实恢复后严格验证，hold父态恢复和exact-state核验后重绑。严格shape(2,)、finite/range、robot/Panda/OSC与原hold/release未改；类外AST和其余生产文件与b596一致，无补零/format_action/额外step。两域、label、网络、阈值和指标不变。

Codex本地：新增provider21 passed（0.63秒），全套1645 passed/12既有可选skip（50.20秒，共1657）；并行独立115 passed（3.08秒）。服务器17个FINISH文件414 passed/0 skipped（56.99秒）。软件证据不冒充真实物理认证。

## 新目录与已核文件准备

- 源码：`/HUBU-AI096/zp/ICML/LIBERO-Remain-stage04-finish-9ddd40f`，228文件逐Git blob/SHA核验。
- 运行根：`/HUBU-AI096/zp/ICML/stage04_finish_9ddd40f`，9个冻结部署文件，原venv/数据/权重/OFT patch不变。
- 纯文件budget/plan-data/register-data均exit0/tee0，无环境创建/标签/VLA；registry语义SHA仍`f8706e9018e618566f53165b50b8e21e6347c089a500cbe3bc21c0930ff8edfe`，证明分组资产未变，不证明物理labels。
- head_train30轨迹/1115待采样帧，head_validation5/198帧，unused15/0恢复；合计同一1313帧真实audit待用户启动。
- registry仍labels_generated=0、ready_for_feature_export=false。实际audit尚未开始，模型rollout预算未消耗。

源码tar SHA `f0c2c3c2f627eb2eeb9d57bb811b5463eaa0e802c56ccb7bc151da6df74693b7`；部署tar `577a27d53a4c33e77af92c9d3e619c6873d009600f8c0691a55cdf3aa2edbbe6`；配置manifest `d8428c2caadffb1bed3f608dee6258a2574beb5210916e34493dc5fb4321233e`；原runtime字节SHA仍`75f2a711a39c58a07715b3a280aeba26a29dfbba70caf87cc051520f0a3f9720`。

服务器JUnit SHA `ab96afbbbf21cd0688083587ee11133ede50ede087cbac1cdad57f48ed9fea10`；registry文件SHA仍`18491d64d5bcc6dfef18dd97f8191aabb1577e111216d0e566a2ee8b1cd15581`。服务器JUnit/plan/registry/三个日志已下载本地项目reports/stage04_task008_r2_fix_2026-10-15/evidence/，逐SHA一致；deployment_receipt.json保存回执，本地两份JUnit与完整源码/配置清单同目录。

## 下一步与禁止主张

用户使用[新R2会话命令](../experiment_plans/stage04_task008_r2_server_runbook_2026-10-15.md)直接重跑同一audit。旧b596 session及失败out/log不再运行、不覆盖；**不新增独立预检、不重新下载HDF、不新增VLA采集**。完成后Codex读取0/1/unknown、完整帧/来源/物理证据，充分后直接到feature/训练，不能自动串联。

尚无真实新标签/feature/head/parity/calibration/eval/视频，不声称停止能力成功；跨域物理祖源unproven与成功示范缺失败/停滞负例限制不变。旧b596的0帧失败、4f单11四步通过、38失败、stage03和脏工作区全保留。真实效果差不是返修理由。

解除R2 P1合并暂停，允许X保留最新协议/Plan4/STATUS及R1/R2/R3、保持实现不变合并PR并登记；Codex不代合并。007/008未closed，交流保留，精确待删清单=[]。本总结、R3及新命令发布后按README本地来源commit/SHA核验归档。
