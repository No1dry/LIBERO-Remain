# Plan4数据来源分组修订：用户已批准方案A

2026-10-14，Codex。当前4f版source0_11四步真实预检已通过；head尚未训练。本提案仅处理数据前置假设，不改Remaining研究目标、动作模型、FINISH指标或停止控制。**2026-10-14用户已明确批准A（复用已下载数据、两个域分组，并承认物理祖源独立性未证明）。Plan4已据此修订，新增008交X实现；本批准不是Codex/X启动真实实验的授权。新代码验收部署前仍不运行真实audit、feature、训练或eval。**

## 问题归属

已校SHA的官方HDF有50条演示、14700个123维states与50个actual XML；与现有50个official init完整向量精确匹配为0/50，init_state属性只是各演示首saved state。公开文件与采集／处理脚本不足以证明演示→评测初态逐一来源对应。

原Plan4在统一source_index空间做head分组，依赖这样的对应能被证明。当前资产不满足这个前提，属于我们的数据设计／证据问题，不是X把文件读坏。不能借demo编号、最近邻、去时钟、宽容差或虚构manual confirmation让旧映射审计通过；0精确匹配也不能反过来证明物理祖源绝对独立。

## 推荐A：明确两个来源域，复用公开普通演示

适用于当前现象验证pilot，最小范围修改是**来源命名／分组和身份校验**；不新增VLA数据采集rollout、不优化动作网络，不改变原5 validation shadow+10 normal active+15 Remain active预算。真实标签恢复、feature、训练、parity仍需用户逐阶段启动并单独计费。

| 来源域 | 分组／用途 | 不能推断的关系 |
|---|---|---|
| 官方HDF完整trajectory | head_train=demo_5..34（30条）；head_validation=demo_35..39（5条） | demo_35不是official init35的声明 |
| 未用于head的HDF trajectory | demo_0..4、demo_40..49保持unused（15条），不按结果替换 | 留这些demo不证明对应eval留出来源 |
| official init | normal_calibration=35..39；normal_test=40..49；Remain=0..4及全部编辑变体 | 数值相同也不是HDF来源同一性 |

上述HDF编号只用于确定**文件中已存在group名字的整轨迹归属**，不是采集seed或eval source_index。分组数量保留既有30/5设计，不挑成功或易例；缺group／类别／独立输入仍报告不足，不自动重选。

明确保证：head训练／验证整轨迹互斥；真实保存state／观测重复跨组检查；不使用任何已编辑的评测输入训练头；head只输入合法当前RGB/proprio/原指令和原同forward动作hidden，不输入source/domain/mask/label/time或GT。

明确限制：**不能据此声称head的训练示范与official eval来源有已证明的物理祖源隔离，也不声称冻结SOG10从未见过该来源。**这是一条较弱但可审计的pilot合同：显式轨迹级隔离＋不直接使用编辑测试样本，而不是偷换“严格同源holdout”结论。若论文要更强源级泛化主张，应采用B或另补真正溯源证据。

## 已批准A的修改边界（详细实现由008任务落实）

1. 分开head_data与evaluation_init身份空间。HDF来源键以文件SHA+trajectory_id绑定；eval键以init文件SHA+index绑定。metadata中明确domain，不把一个domain的整数用成另一个domain的来源。数据分组、head_validation与normal_calibration命名分开。
2. HDF审计不再为了训练强求0..49全部eval来源都有对应演示；仅检查预定head_train/validation真实轨迹完整，另外保留固定eval registry与组归属。不得用collection_provenance字段伪装HDF→init关系。
3. audit/cache/head/normal校准/job/parity的身份消费者一致迁移或显式版本区分，旧结果只读保留，不混用旧统一source语义。head选择epoch的BCE验证输入来自head_validation；32输入parity也来自该组，不借测试；阈值只来自normal_calibration的5条shadow。
4. 原物理标签合同不改：当前全部目标+真实释放，再从同一保存状态做K4被动保持；unknown不造正／负标签，未来示范动作与is_last不是标签依据。actual XML、layout、原始输入hash、类别覆盖、source/profile／模型身份检查保留。
5. 继续冻结原动作网络与MLP结构／超参数，保持一个固定runtime的crop/seed/chunk，指标及H520/W150不改。两域修改不是调参救分，停止能力差先如实报告，不用test改阈值或换组。
6. 新namespace规则和泄漏拒绝需CPU/fake测试、实际CLI/runbook；Codex软件审查与新目录部署后，才由用户启动真实audit。首次真实audit先检查class coverage／unknown及数据identity，不直接串到训练。

## B：保留严格同源隔离，新增可追溯普通轨迹

若用户不接受A的物理祖源限制，保留官方source层面的严格训练／验证／测试划分，需要真实采集记录，或由指定official init产生新的normal00轨迹、保存完整采集与变换provenance。只采已确认的train/validation来源，测试来源只做独立注册，不为审计覆盖而采test训练轨迹。

这是新增数据采集阶段，有额外VLA forward／仿真／录像与标签费用，**不包含在原30条eval预算内**。需要先明确冻结来源、条数／H、失败处理、记录字段与费用上限，再给X实现collector和用户命令。不能自动采集、对失败源挑容易替代、只保留成功以假报来源覆盖；同样不保证有足够正类或普通stop能力。

## 决策与科研边界

用户已选择当前pilot采用A，先建立诚实的stop-aware frozen-base参照，报告突出来源隔离限制。Plan4原统一source假设已由这个明确批准的合同替代；B仅保留为更强来源级验证备选，不新增其预算。当前旧4f代码还采用旧审计，仍不能直接训练，008实现经审查部署后才能由用户启动audit。

两条路径都为排除“没有FINISH接口／没学普通停止”的混淆服务，**不是把原模型分数做低或用FINISH补救动作规划**。正常停止校准／独立active若不足，不能宣称已完全控制这个混淆；Remain错误需结合goal/placement/stop诊断如实解释，不改预定指标救成绩。

当前已批准A，Codex已写[008完整任务](../../collaboration/tasks/008_finish_data_source_domains.md)。X先按既有授权处理已accepted PR #4，再独立实现008；Codex审查部署、用户启动audit。B未经授权，不自动采集或扩大预算。阶段未closed，原文件不删。
