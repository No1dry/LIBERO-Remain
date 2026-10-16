# 009：最小释放可测性诊断——init35原动作前缀重执行

2026-10-16，状态open。**用户已明确确认“同意最小诊断”**：X实现独立诊断入口；Codex审查、纯文件准备和部署；真实native作业仍由用户亲自启动。不是改release／校准协议，不授权重训、重打分、扩大数据或追加其他轨迹。

## 目标与分支

解释basket_s035_00在step280“入篮、无grasp/contact但release unknown”的几何来源。只记录evaluator-side测量，不输出新成功率／新释放标签，不改现有旧判据或原calibration。原uncalibrated结果继续保留。

基准为已审生产实现3433f487d38efe0a08e4c814e87412aad5aba9fe；X只读回复HEAD54364ebb579d38a81d2d9396585d084cb9ac21da与基准无生产diff。PR #5已有R9 accepted：X可先按README/R9合并已审实现，保留最新main的R11/009文档，再开独立009分支／PR；Codex不代合并。若009先基于PR5分支开发，明确依赖与固定基准，不能从缺008实现的旧main拼接接口。保留无关脏工作区。

## 1. 精确输入与预算（默认不可放宽）

原服务器根/HUBU-AI096/zp/ICML/stage04_finish_3433f48；原采集results/run01/validation_shadow，run_id65c8ef90d9d7495ebc8234cb814e3b5a。

- run.json文件SHA：0c0fa4803d1e7a8a9b1a3a1ab2fe15f55c7b2e35a66436117d2fddd60283fb9b。
- 唯一episode：basket_s035_00；raw/0000.json SHA049ac123d348402177c30c9b2915b88e9573ea3bed18663c0f1fcc3eb6af3e78。
- 原normal-bank：/HUBU-AI096/zp/ICML/stage04_finish_2cb1428/results/run01/normal_bank/normal_bank.json；文件SHA084e55537c25e515153e48624d807483b3348f9cee67db77425f69d5eaa6080c。
- 必须用episode中原bank保存的已settle初态sources/035/states/basket_s035_00.npy，SHAe1d42bfb1aa9c21e52615e95e8f834eedbf361592c259d654e5a807423ba408f；不是直接载原official init35、不是从263/280中途restore。
- 原模型XML SHAdad2437d1c2f8cbff26232c252f241978ce7de02cc6e34da0267fc94f4607163；BDDL SHA2e661058917f683a25bce480015197f0a2c1911bcbc2b9dd9d947199069c9618。
- 最多顺序执行原executed_actions的step1..292，全部policy动作，float64逐值／逐bit与原动作绑定，不重新clip/重采样/改gripper。
- step0及执行后1..292共最多293快照。292为原query37（观测step288）的chunk_index3；**292处没有query**。不执行293..296，不begin_hold、不插入FINISH、不做W150。
- 292条是20Hz控制步，不等于native mj_step次数；初始化/reset/restore及控制步内substep分别计数并记录time变化。保留原初始化必需的native调用，不重犯“禁止一切mj_step1导致原reset失败”；但不允许额外诊断step/reset/forward刷新数据。
- VLA forward、head inference、processor调用、训练均0。不自动追加init37、其他四条、normal_test或Remain，不换MuJoCo/robosuite版本。

## 2. 最小接口与纯文件计划

建议独立模块benchmark.remaining_goals.finish.release_audit，避免改现有run/runner/release/calibration默认路径。提供plan（纯文件）与run（用户native）两个明确入口；若用等价独立CLI，请交完整实际参数，不写不存在的候选flags冒充已实现命令。

plan至少接收source-run、episode-id、max-action-steps=292、新out，验证上述身份／bank／原动作和query ledger；固定只允许35与292上限，保存新计划和输入文件SHA。不能因为原calibrated=false拒绝诊断。--help和plan不创建native env、不加载研究头／VLA。

run只消费已冻结plan及新out，先重新核全部源SHA，确认目录全新；再创建唯一FinishLiberoEnv并调用原reset/step语义。为旧版本artifact记录各自来源，不要求其implementation hash等于新诊断代码。输出raw诊断只读，不触碰原run/calibration/head/cache/bank；无自动resume或重试。

## 3. 动作、观测与一致性

复用原FinishLiberoEnv reset／step和runner观察／evaluator顺序（含原fresh_observation），不要复制整套环境以引入新动力学。记录器只读已有native数组；不能为凑证据新增forward/controller.update/render/step。原初始化／step内部本来有的调用允许且单列计数。

- step0比原initial observation；query边界0,8,...,288比raw queries中**原始observation_sha256**，使用相同_observation白名单、dtype与hash口径，不与processor后tensor/crop hash混比。仅记录“原query对照”，不调用policy或增加假query。
- 每步比旧goals／targets released／grasp/contact／两clearance／动作及phase，记录first_mismatch。JSON浮点还原后尽量逐bit/同确定序列；若确需数值容差，必须在运行前声明字段和理由，不能看重放结果再放宽。
- 默认首个不匹配即停止并保留partial，分别记录obs/render hash、物理truth/geometry或action差异；不能把偏离轨迹的测量回写原帧。不得自动重采或把不匹配“修正”为成功。
- 即使对照通过，只能称“从原初态重执行同动作前缀、可观测证据匹配”；原run没完整native checkpoint，不能宣称原step280的全部不可见solver/controller状态已被精确恢复。
- 不强制新增MP4；可保存原env.step已生成的关键帧PNG及索引（263/272/280/288/292），不额外native render，不用视频像素自动改物理标签。

## 4. evaluator-side sidecar（只记录，不实现新释放判据）

新schema可采用remaining-release-observability-audit-v1，独立于原FINISH输入／结果／calibration版本。所有状态／几何／GT仅在诊断侧，绝不进入模型观测／特征或GT停车路径。

一次性静态记录：实际XML/资产/源码/依赖SHA，model维度与相关名字→ID映射；两个目标、全部gripper contact geoms及两pad组的body/geom集合、type/size/rbound/dataid、碰撞mask/过滤/margin/gap及相关编译mesh表示和变换。足够定位到底哪对外包界导致最小间隙；不以渲染面替代碰撞语义。没有实现更紧外包体／精确距离或新label的授权。

逐帧记录：step/action_kind/原query对应关系，原goals/released及完整旧release evidence；相关geom_xpos/xmat、目标/hand/pad位置与原包络计算所需数组／最小对；现有contact pair/dist/pos/frame及过滤信息，接触力若读取需注明接触坐标系／时刻，不把力单独当release。缺/非法/非有限值报诊断技术错误，不能混作物理unknown。

native状态保存：固定2.3.7的mjSTATE_INTEGRATION mask及mj_stateSize/getState取得的typed向量、time/ctrl；另外记录可获取的OSC目标、gripper.current_action及相关Python/NumPy RNG。静态API符号不等于真实native成功，实际run必须记录backend/runtime版本／库hash。**这是新重放的诊断快照，不承诺通用resume/checkpoint系统；不实施mj_setState恢复。**

记录器前后对integration state、ctrl/gripper/controller关键状态和RNG做指纹，证明无修改。不要追加native计算补接触，不升级依赖：服务器包元数据MuJoCo2.3.7、robosuite1.4.0及头文件已由Codex核过，该固定header无mj_geomDistance；不偷偷改margin/mask、调mj_collision或用新API改变接触数据。官方依据见[2.3.7 API](https://mujoco.readthedocs.io/en/2.3.7/APIreference/APIfunctions.html)及[接触/碰撞说明](https://mujoco.readthedocs.io/en/2.3.7/computation.html#collision-detection)。

## 5. 输出、异常与CPU/fake验收

计划／运行输出全新目录，逐文件SHA清单及typed NPZ（no pickle）／JSON，不覆盖任何历史原文件。summary必须区分plan_ready、diagnostic_completed、replay_mismatch、technical_error、interrupted；报告请求/完成控制步、snapshot数、每类native调用计数、初始化与动作期时间、VLA/head/processor=0、first_mismatch、旧判据与测量覆盖。不能输出calibrated=true、正式阈值或新benchmark成功率。close始终执行，异常保留partial，不开爪／step来“收尾修复”。

CPU/fake需实际覆盖：输入SHA/episode/index/bank替换拒绝；初态不是raw official或中途状态；292边界无第293动作／无292query；动作dtype/顺序/phase精确保留；原query hash口径与观测差异；旧truth/clearance/action不匹配首处停止；记录器只读指纹／RNG；非法geom/contact/native形状／非有限值；新输出防覆盖；初始化/step计数与清理；禁止任何policy/head/processor真实入口。fake诊断不得冒充native认证；不导入torch与不做NN调用是不同要求，LIBERO传递依赖不应造成假失败。

保留既有FINISH回归；报告新tests passed/skip理由及生产diff，确认仅新诊断／CLI/测试/文档，原release/calibration/训练/控制／指标/数据分组／阈值网格未变。X不运行真实native／模型／训练，不自行合并009或改旧分数。交009_round1、实现/最终SHA／PR、可复制纯文件plan与用户run命令，实际服务器路径由Codex部署后填齐。协议修订、296步K4确认、W150或init37另需用户明确授权。

[008 R11裁决](../reviews/008_round11.md)，[审查与授权记录](../../docs/stage_summaries/stage04_release_audit_proposal_accepted_2026-10-16.md)。本任务open、Stage04未closed，精确待删=[]。
