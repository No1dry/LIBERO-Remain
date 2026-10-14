# Stage04 新版11真实预检通过：单样本四步接口检查

2026-10-14，Codex审查；用户亲自启动。冻结源码4f76f4917a9174fc5b80ef83e3cf21eaf053c98d，episode=basket_s000_11。旧38版技术错误另存，不混入本版分母、不倒改。

## 已核结果

报告status=recorded／error=null；日志command_exit=0／tee_exit=0。实际trace顺序完整0..4，四个7维动作有限，最后一维gripper全部0，之后三步有微小pose纠偏，最大绝对pose输入约0.000546；不是冻结仿真或仅重复render。

| 检查 | 结果 | 百分比含义 |
|---|---|---|
| 请求的真实保持步 | 4/4，100%完成 | 实际动作步数，不是模型成功率 |
| 两目标同时保持满足且已释放 | 5/5检查时刻，100% | 同一轨迹的0..4时刻，不是5个独立episode |
| target release unknown | 0/5，0% | 仅当前已释放11样本 |
| VLA模型调用 | 0 | 没有FINISH模型决策、训练或eval |

实际robot类型为libero.libero.envs.robots.on_the_ground_panda.OnTheGroundPanda，gripper为robosuite.models.grippers.panda_gripper.PandaGripper；OSC_POSE／fixed／world pose latch，保留原finger目标。两个目标各时刻都没有双pad grasp或gripper接触，所有手／pinch包络clearance大于工程margin0.002m：Soup最小hand/pinch约0.213779/0.240195m，Sauce约0.245793/0.273213m。release=True与这一远离夹爪的证据一致，非目标物体未被判为新入篮。

初始观测NPZ字节和规范observation SHA均与原source001保存的观测一致；agentview和wrist均256×256×3。来源、相机、原指令及运行环境没有为通过预检而改变。204源码／4部署文件复核一致。

## 验收范围与限制

**接受这一个已释放11来源的四步接口预检**。R2机器人类型误拒绝已在真实路径中确认修复，调用保持／状态判定／初始观测保存／资源退出链路可运行；本次不需要X返修。

不能把本结果说成VLA学会停止／自主发出FINISH／能重新规划剩余目标，也不能声称W150保持、所有来源、夹持状态的释放判定或整个benchmark通过。当前只一个source0_11，未测试抓住目标／单指接触／部分任务场景；每步末端位置、旋转与finger qpos未独立存入trace，因此不报告全程位姿漂移为0或手指实际位置完全不变。hold_contract的empirical_stability_validated=false按源码原样保留，不改原raw。

这不是五条模型评测，也没有新的CFS/JSR/UIR成绩。默认30条模型rollout预算尚未消耗。

## 剩余前置问题与下一步

HDF演示与official init逐一来源对应仍未建立，训练不放行。不要重复运行已经完成的11命令，也不为此改依赖／模型／指标。用户已明确批准[两个来源域方案A](../experiment_plans/stage04_data_domains_proposal_2026-10-14.md)，Plan4已修订、Codex给X[008独立任务](../../collaboration/tasks/008_finish_data_source_domains.md)。批准A替代旧统一source映射前提，仍不把demo编号写成init编号，也不自动开始训练；需新审计代码验收后用户启动真实audit。

已批准当前pilot复用已下载普通演示：head按完整HDF轨迹训练／验证，official init单独校准／测试，清楚披露跨域物理祖源独立性未证明。若坚持严格同源留出，需要新的可追溯普通轨迹与另行预算。两条路径都不改核心Remaining问题、不把低分作为选组依据，也不训练已编辑测试状态。

## 原始证据与归档

服务器：`/HUBU-AI096/zp/ICML/stage04_finish_4f76f49/results/run01/environment_preflight_11_r2/`；日志在同运行根logs/run01/01_preflight_11_r2.log。本地已取回原文件，位于`/Users/zhangpeng/Desktop/Learning_Not_to_Act /reports/stage04_r2_preflight_result_2026-10-14/evidence/`，没有重新生成或重跑。

| 文件 | SHA-256 |
|---|---|
| preflight.json | 83c7dc7ded9932bc20c51e071ba1c3d65708eb9791dd23879a6c28b78f8c388e |
| 01_preflight_11_r2.log | 89d7fb34aa2028b6db4a1d7b14e22ffbd52c11caaecf0261138a46750346551e |
| initial.npz | a4bae24b736739626db6cbc6b8d60f3525db7beeee22792c92567cf1b30ffed6 |

规范observation hash=92e0d7689cd9867a77a0fc9eb1bce4719b060a186c0ae7b5e0915acb4439c92d。Codex只做报告、日志、hash／NPZ验证和源码审查，未启动新真实作业。旧失败／新成功均保留，007和Stage04尚未closed，待删清单为空。

下一步操作：X按008修改审计／身份接口并交CPU/fake证据；Codex审查部署；用户按新命令启动真实audit，类覆盖和unknown通过后再到feature/训练。当前不启动训练。
