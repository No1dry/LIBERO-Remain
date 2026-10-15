# Codex：008 Round 2——真实audit初始化顺序P1

2026-10-15。**changes_requested，仅此明确运行时错误；不要重做008数据域设计。** [PR #5](https://github.com/No1dry/LIBERO-Remain/pull/5)冻结b596af26e167450beb7f3c7fe61b6dfd53523ef6的首个用户真实audit在采样前退出。R1关于两域消费者的审查与CPU结果保留，但不能据此声称真实audit已可用；本P1修好验收前暂停合并/运行该版真实audit，不覆盖旧产物。

## 已核证据与根因

命令为已部署session的03_audit。真实输出status=insufficient，issues=[audit_error / ValueError / invalid Panda current_action]；command_exit=2、tee_exit=0。provider_identity={}、restore_attempts=0、hold_attempts=0、rows=0。因此没有标签、没有类别覆盖结论，也没有新的模型失败率。这不是HDF分组不足或原始模型能力差。

- report：`/HUBU-AI096/zp/ICML/stage04_finish_b596af2/results/run01/audit/audit.json`，SHA `d9b6e03249a3a0efdbdbb17a25af21d5614023f51ffe2b5fb1c443243db486ee`。
- log：`/HUBU-AI096/zp/ICML/stage04_finish_b596af2/logs/run01/03_audit.log`，SHA `68de946734df6f3b705023fabf960069dab9e58206a35a781d8184582e75c573`。
- 两份已下载本地并与服务器SHA一致；旧38/4f/b596及本次失败全保留。

实际服务器robosuite1.4.0源码：GripperModel初始化`current_action=np.zeros(self.dof)`，PandaGripper.dof=1，所以刚reset时合法内部状态是一维。该内部状态不是saved MuJoCo state中的两指关节位置。Panda.format_action中的两元素广播或既有restore_raw_state/_synchronize_grippers才会形成两执行器命令。只看Panda dof=1、却假定reset已完成两指命令同步的fake覆盖不够。

本仓环境文件：

1. `benchmark/remaining_goals/finish/environment.py:381`：provider构造在reset_scene后立即BasketContract，触发_robot_contract:99的严格shape(2,)检查，尚未调用restore_raw_state。
2. **同文件:407也有同一顺序问题**：reset_from_xml_string之后、真正restore_raw_state之前构造BasketContract。不能只修第一处、让下一次用户运行才暴露第二处。
3. 已验preflight走LiberoGoalEnv.reset→restore_raw_state→_synchronize_grippers→再BasketContract；因此4f预检通过与这次provider失败不矛盾，不能用它替代audit路径覆盖。
4. restore_demonstration已有:423的restore_raw_state后:425重建合同，hold分支finally已有恢复后:457重建合同；这些是正确的验证时点。

实际安装源码SHA：panda_gripper.py `a3760a8fc4599fa6f79914304b82466f3c1bda1a945943ca693bb57f00dc59eb`；gripper_model.py `0543b5a9e1d8b41e21880d8445c5d8fbf8535a4ac6fd55c5e70a3b1f323c3735`。Codex只读取源码/证据与CPU fake，没有代跑真实恢复。

## 最小修复要求

建议推迟上述两处提前合同构造，直到已验收restore_raw_state成功、真实恢复的finger qpos/position-servo command已同步后再构造；可有等价合理实现，但须保证下面不变项。不要为初始化虚拟默认场景做一次额外物理step或单独重跑11预检。

- 保留_robot_contract严格shape(2,)、finite/range、两类robot、Panda/OSC全部安全约束；不要泛化为接受任意shape、repeat/补零、吃掉异常或跳过真实验证。
- 不用format_action(0)冒充从saved finger qpos正确同步的目标；不额外env.step、settle、开爪/闭爪、加动作或改HDF state。
- provider构造的base layout/XML/BDDL/原指令检查、source XML layout检查保持；允许在第一条真实恢复完成前contract=None，但任何truth/hold必须已有本条恢复后的有效合同。
- 每个XML切换/连续帧恢复/hold独立分支及finally父状态恢复都在正确时点建立合同；不能复用上一XML或上一state的陈旧contract。异常仍关闭资源并保留partial。
- 不改008profile/split/keys/identities、采样1313帧规则、GT/label/unknown、FINISH控制、网络、阈值和指标。不能把空audit标ready或跳过标签直接训练。

## 一次补齐的CPU/fake回归

X不运行真实仿真/模型/科研训练。用最小fake native reset明确产生current_action shape(1,)，XML reset也回到shape(1,)，真实restorer的fake只在被调用时按受控已知qpos建立shape(2,)：

1. provider完整构造不在同步前失败，不调用step；首次restore与换XML路径均先restore再检查合同。
2. 同XML连续不同finger姿态不可沿用上一帧目标；hold分支恢复父状态后合同重新绑定，观测仍在hold前保存。
3. 在应验证的阶段，未同步或非法shape/NaN/越界仍拒绝；构造/恢复/XML不兼容异常关闭资源，原始partial不丢。
4. 至少一个端到端tinyHDF/fake provider生命周期回归，真实调用本provider类而不是全用绕开它的FakeProvider；负类/正类hold的调用顺序可审计。不要只测替代provider声称修好。
5. 原Panda兼容性、FINISH、数据域及全套CPU/fake回归继续通过，列真实结果和未做真实阶段。

更新response008_round2，给精确SHA/生产diff/测试/候选命令。按最新main文档保留R1与本故障记录，不扩成新架构或数据计划。Codex验收后新不可变目录部署，用户在**新out/log**只重跑同一audit；不用新增独立预检、重下载HDF或新VLA采集。失败目录不可覆盖，旧完成的00_budget/plan/registry也不是模型实验成绩。

下一步：**X修两处初始化顺序和对应回归；Codex快速审查部署；用户启动同一真实audit，充分后立即进入feature/训练。** 原007/008交流和阶段证据均不清理。
