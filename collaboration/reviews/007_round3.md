# 007 R2修复复核：软件accepted，新冻结版本已部署

2026-10-14，Codex。裁决：**accepted（R2的P1机器人类型兼容性修复）**，无需返修。007代码范围恢复软件accepted，但真实物理预检／来源分组／停止能力仍待验证，Stage04未closed。

## 冻结版本及变化范围

- PR #4交付head=`4f76f4917a9174fc5b80ef83e3cf21eaf053c98d`；Git tree=`41ddba3b0ad52dbb728c12d74e38c942a2357134`。
- X测试实现=`a7dda8d28e35c93aa8eead675075b113612f7d15`，与最终head仅STATUS及[007_round2回应](https://github.com/No1dry/LIBERO-Remain/blob/4f76f4917a9174fc5b80ef83e3cf21eaf053c98d/collaboration/responses/007_round2.md)不同。
- 相对旧38版，生产代码只改finish/environment.py（25行增加、3行删除）；其余实现改动为对应测试、固定LIBERO源fixture、来源说明与MIT许可。合入的main更新仅协作文档，没有夹带实验代码或修改协议。
- 隔离临时源码审查，204个文件逐GitHub blob核验一致；本轮没有pull/reset任何既有dirty checkout。

## 必须项复核

1. guard精确识别`robosuite.models.robots.manipulators.panda_robot.Panda`和`libero.libero.envs.robots.on_the_ground_panda.OnTheGroundPanda`，没有以isinstance(Panda)误拒直接继承ManipulatorModel的官方类，也不宽泛放行所有含Panda名字的类型。
2. PandaGripper／dof1／speed0.01／有限2维current_action及范围、fixed-impedance 6D delta orientation OSC、limits/interpolators等检查保留。保持当前末端pose与finger目标、gripper=0、无GT开爪／修复，公式及动作执行未改。
3. fixture逐字节等于此前从服务器备份的固定OnTheGroundPanda源文件，SHA=`7d580aeee632e164f327cf6b1951861bec40cf814cdbe92bcfc469a93e1f9fa8`。CPU测试仅执行固定class AST与非物理基类，不import/初始化LIBERO，不加载XML。回归正例保留真实namespace/独立继承/默认Panda XML和gripper；非法robot、gripper、OSC负例均在任何更新或step前拒绝。
4. hold_contract增加实际robot/gripper类型，仅进evaluator取证。schema允许该contract字典，evidence完整deepcopy/hash绑定，因此不破离线验证、不进入policy输入；partial/close路径不改。
5. FINISH/STOP/schema、H520/W150/chunk8、active/shadow、release unknown、禁止投放、相机、权重、依赖、source/split/原始数据全未变。

没有新阻塞，不因偏好增加改动。R2精确P1已在软件范围解决；**不因此宣称真实保持／释放预检已通过**。

## 独立CPU/fake测试

| 范围 | Codex实际结果 |
|---|---|
| 本地10个FINISH文件 | 261 passed / 0 skipped，8.06秒 |
| 本地全套 | 1492 passed / 12 skipped，30.69秒，共1504项 |
| 新部署服务器10个FINISH文件 | 261 passed / 0 skipped，23.17秒 |
| 独立交叉复核 | environment+evidence 68 passed，0.45秒 |

本地12个既有skip为11项未安装的可选固定BDDL文件核查、1项缺imageio_ffmpeg；X Windows报告1489 passed/15 skipped的差异来自已有平台／依赖skip，不混写同一次测试。全部为CPU/fake／合成数据，没有真实sim restore、VLA、真实数据训练或物理4步测量。

| JUnit证据 | SHA-256 |
|---|---|
| 本地finish-review-junit.xml | `e9fc5d176a41aa2fa1b84082b12fd86bea2b4d89ed12d69e62fd10ee3e3121a6` |
| 本地full-review-junit.xml | `484f6e20ca85fa17208240bff8ec7b62a922dd4a20b970c97a670f39978cf599` |
| 服务器server-fake-tests.xml | `0198e7f616bb31d7e60b974b5b1908182a7205c0bfeb719b717e1ca6224f2968` |

本地证据目录：`/Users/zhangpeng/Desktop/Learning_Not_to_Act /reports/stage04_r2_fix_review_2026-10-14/tests/`。

## 已部署与用户启动命令

新源码快照：`/HUBU-AI096/zp/ICML/LIBERO-Remain-stage04-finish-4f76f49`；新运行根：`/HUBU-AI096/zp/ICML/stage04_finish_4f76f49`。204源码＋4个冻结部署文件上传后核验一致，服务器CLI帮助和日志包装器通过。复用原sim runtime，不升级或生成新状态，源码快照无.git，用source_inventory核验。

本轮只配置同一source001、同一replay、同一个basket_s000_11预检；新日志／out不会覆盖旧失败。完整命令和检查点见[新版本单预检runbook](../../docs/experiment_plans/stage04_preflight_r2_runbook_2026-10-14.md)。

X无需追加纯意见轮次；可按既有授权合并保持已审实现的PR并登记merge SHA，Codex不代合并。若改变实现必须列明新diff，不把新代码自称同版已审。

旧38版preflight.json／日志仍SHA=`901110a227de747596d3acfd8bdc4c853c242b00b311dd902b12f371ba9eaaf0`／`06e1662cc6241a8818772fc7356adbf67386ab133e42846d335ce46b2eabcc9e`，历史失败不倒改。

目前只有“软件修复accepted＋新源码部署完成”，新真实preflight尚未由用户启动。HDF来源精确映射仍0/50，不自动授权audit／feature／训练／后续eval。007及Stage04不标closed，开放交流及原始实验数据全部保留，待删清单为空。

下一步操作：用户启动新冻结版本同一11的4步物理preflight，Codex读取真实报告检查pose／release／unknown；之后另行决定来源分组方案。执行者：用户启动，Codex结果审查；X本轮修复已通过软件验收。
