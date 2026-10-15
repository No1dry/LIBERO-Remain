# Stage04：用户授权的零积分布局诊断与受限兼容裁决

2026-10-15。用户对“仅加载场景/导出布局，不任务动作、不label/VLA/训练”的明确请求回复“继续”。Codex按此执行一次最小诊断，未获得或使用全面实验启动权限；后续真实audit仍由用户启动。

## 原因已定位

冻结089e0b7，默认scene与首条实际demo_10：nq65/nv57/nu9/nbody29/nsite23/njnt17，全部17 joint names/type/qposadr/dofadr完全相同；_layout仅ngeom/geom_names/geom_bodyid不同。默认161 geom，demo162，在ID73多一个robot0_link7_collision，父body robot0_link7、mesh同名；其余geom ID因此后移。只在比较副本排除该项后整个_layout与默认精确相等，包含7个匿名geom，不能用set/dict丢弃它们。

新增geom是原示范模型的真实差异，可能影响接触/图像/K4，不是已证明物理等价的“纯ID重排”。原XML不得删/禁碰撞以凑默认数量。完整XML另有两个番茄geom quat末位0.663328→0.663329和辅助camera paperview/canonical_agentview差异，不能称完整模型唯一差异；共同agentview和robot0_eye_in_hand属性相同，50条HDF原XML的额外geom/选定camera静态签名一致，但仅编译比较demo_10。

基准compiled XML SHA dad2437d1c2f8cbff26232c252f241978ce7de02cc6e34da0267fc94f4607163与既有source001一致；demo compiled SHA b97ae2c76617c06aa6006e1818b34a4f5c37c4d18a2762d32e0e96afb198055b。关节状态解释未在该样本改变，不代表动态效果相同。

## 诊断边界与透明记录

layout01防护把初始化调用的mj_step1也拦住，在环境完成构造前退出，保留错误/日志及EGL清理警告；不是新的benchmark错误。查固定源码与[MuJoCo2.3.7管线](https://github.com/google-deepmind/mujoco/blob/2.3.7/src/engine/engine_forward.c#L809)，该阶段做位置/速度派生量计算，积分在后续阶段。layout02保留对任务step、mj_step和mj_step2的阻断，仅包裹初始化mj_step1，并逐次检查time/qpos/qvel/act/ctrl字节不变。

layout02 recorded、exit0/tee0：一个环境、一次显式native reset、一条demo XML加载，时间始终0；两次非积分初始化阶段均上述物理/控制字节完全不变。任务动作0、积分调用0、HDF state恢复0、label0、VLA0、训练0，环境已close。没有试跑audit、重采或使用GT选择停车。

报告/两份模型XML/两份layout/完整diff及两次诊断日志位于服务器stage04_finish_089e0b7/diagnostics/layout01、layout02与logs/run01/layout0*_diagnostic.log；已下载项目reports/stage04_task008_layout_failure_2026-10-15/diagnostic_evidence/共9份，逐SHA核对一致。成功报告SHA2966b2bf8f75075a78a3de81874c6b3fc39cc1e9018c22367fc1c7d4dc08a5cd；diff SHAbe8cc1202de9bdfbed23541553db31c8b102cdf342ace8da05e868bb9c243c64；成功日志SHAa2363ef939a4031b4e80e99fcfb451334ddfd9f6a0183bf674ba774120258c30。首版失败报告/日志也保留，不删除来伪造一次通过。

## 研究与实施裁决

此前方案A已明确要求actual官方HDF XML；只在head示范审计域支持这个已核、来源冻结的原生模型变体，是原方案的实现完善，不另选A/B。**不改变benchmark eval/source001，不改scene/state，不改标签定义、释放/K4/网络/阈值/评分**。head源模型→eval模型的额外差异须明确披露；普通停止独立验证仍必要，未来失败不能仅归因于remaining-goal重判定。

[给X的R6详细边界与测试](../../collaboration/reviews/008_round6.md)与[CPU可重放的实际布局证据](evidence/stage04_task008_layout_diagnosis_2026-10-15.json)。未知模型/关节/匿名几何变化仍严格拒绝；不全删guard、不按basename/name集合猜、不借更改相机或禁碰撞放行。该项软件实现尚未交付，当前真实audit仍0标签，没有新模型分数/视频。

下一步X最小兼容实现→Codex审查/新部署/完整命令→用户重跑原audit。无新增独立预检、HDF下载或VLA采集；本次授权不自动延伸到真实audit/label/模型训练。R5资源结论及所有历史失败保留，007/008/Stage04未closed，精确待删=[]。总结/审查/证据/STATUS提交后按README本地来源commit/SHA归档。
