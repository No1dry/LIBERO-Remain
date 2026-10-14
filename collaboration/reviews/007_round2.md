# 007 第二轮：真实预检确认的机器人类型兼容性错误

2026-10-14，Codex。裁决：**changes_requested，限于一个明确P1接口错误**。不是因为停止能力或分数差而返修；不增加模型／数据／指标需求。R1的CPU软件验收记录保留，但新证据使未修正版的真实FINISH实验入口被阻塞。

## P1：固定basket的OnTheGroundPanda被类型检查错误拒绝

冻结head=`38e6a449d4e769b842e10c5b393fc2b26a5cfa2b`，PR #4仍open／未合并。用户于2026-10-14 14:56（Asia/Shanghai；日志UTC06:56）启动已有`basket_s000_11`预检。结果：

- `status=technical_error`，`command_exit=2`、`tee_exit=0`；
- error=`RuntimeError: unsupported Panda/gripper incremental-action contract`；
- trace=[]，model_calls=0；未记录初始观测artifact、hold_contract或任何4步hold状态；
- 原始目录与日志保留，没有Codex代跑或补重试。

原因位于本head的`benchmark/remaining_goals/finish/environment.py:75–78`：robot_model类名必须恰为Panda。固定LIBERO8f1084的living-room task实际把输入Panda映射成**OnTheGroundPanda**，必定不满足此条件。

已读服务器有效源码与安装包，不是猜硬件／类名：

1. `libero/libero/envs/env_wrapper.py`默认robots=[Panda]，默认OSC_POSE及default gripper；
2. 固定`envs/problems/libero_living_room_tabletop_manipulation.py:23–25`把robots改为OnTheGround前缀；本任务是这个living-room domain；
3. 固定`envs/robots/on_the_ground_panda.py`定义OnTheGroundPanda，使用Panda robot.xml，default_gripper=PandaGripper；**该类继承ManipulatorModel，不是Panda的子类**；
4. 有效robosuite1.4.0的PandaGripper是dof1／speed0.01／2维current_action／sign增量形式；0仍保留原目标，不需要换抓爪控制协议。

[固定LIBERO任务映射](https://github.com/Lifelong-Robot-Learning/LIBERO/blob/8f1084e3132a39270c3a13ebe37270a43ece2a01/libero/libero/envs/problems/libero_living_room_tabletop_manipulation.py)、[固定OnTheGroundPanda](https://github.com/Lifelong-Robot-Learning/LIBERO/blob/8f1084e3132a39270c3a13ebe37270a43ece2a01/libero/libero/envs/robots/on_the_ground_panda.py)。对应服务器文件SHA分别为`a13bc0a92ff746d572a6d76e09add98dafad70d88928555068728641c6c9de10`与`7d580aeee632e164f327cf6b1951861bec40cf814cdbe92bcfc469a93e1f9fa8`。

精确失败阶段：`FinishLiberoEnv.reset → super().reset → BasketContract → PandaPoseHold → _robot_contract`。恢复后的停止模块合同检查抛错，`reset`未向preflight返回观测，尚未执行begin_hold或hold_action。不是模型输出错误，也不能称4步保持成功/失败的能力评测。

Codex已用原有Native CPU fake仅改变robot_model类名复现：Panda通过，OnTheGroundPanda被同一error拒绝。没有真实环境重建或forward。R1 fake只用了Panda，Codex之前没有覆盖真实LIBERO类型，漏掉此兼容性错误；CPU通过仍是软件证据，不改写为真实通过。

## 给X的最小修正要求

### 必须修复

1. 正确支持当前固定basket实际使用的OnTheGroundPanda，同时保留已支持Panda或同等受限实现。可以使用明确受支持类型识别＋实际控制合同验证，方式由X决定。**不要只改成isinstance(Panda)**，因为真实类不是该子类；也不要接受所有名字带Panda的任意robot。
2. 不放宽实际PandaGripper/增量动作、dof1/speed0.01、有限2维current_action、fixed-impedance 6D delta OSC_POSE、姿态／控制范围等已有条件；保留当前pose与finger目标、gripper=0、无GT开爪／补救的行为。
3. 新增CPU/fake回归覆盖真实OnTheGroundPanda识别及其PandaGripper/OSC合同。用对应真实类型／namespace的受控fixture或源码约束检查，不只把原Panda测试重新命名后称真实覆盖。继续测试不支持类型／不兼容夹爪／错误dof或speed／错误controller被拒绝；未知硬件不fail-open。
4. 保留旧FINISH/STOP/schema、H520/W150/chunk8、active/shadow、release unknown与禁止投放语义；不换仿真依赖／checkpoint／camera／source／原始数据／指标／split。这个错误不需要训练或降低安全条件。

### 建议但不另设返修门槛

- 将笼统contract error拆成可定位的robot/gripper/controller字段差异，记录实际qualified type、dof/speed与具体拒绝项，防止同类排查重复。正常hold_contract可带实际实现身份；这些只进evaluator证据，不进入policy输入。
- 确认错误与close路径仍保存partial并关闭资源。源码静态核对本次有效OSC1.4.0的set_goal/scale/update接口，没有发现另一项可确证的新不兼容；真实pose/release仍由用户后续预检。

## 测试与交付

X仅做静态／CPU-fake软件测试，不启动真实仿真、data restore、hold、VLA、训练或eval。交`collaboration/responses/007_round2.md`，引用新实现SHA／PR、精确diff、新增回归、实际test数量、未运行真实阶段。

至少复跑10个新增FINISH测试文件和整套纯CPU tests；类识别和拒绝分支的回归需明确列出。不要用真实GPU/效果来验证此软件修复。没有新实现前，不按R1的历史accepted合并或发布原38e6a44；Codex不代合并代码。

Codex验收后部署**新冻结SHA到新目录**，提供新的session、日志名和out。不要就地改已部署38源码或重算manifest绕过身份校验。用户再亲自启动同一source0_11的4步预检；旧失败目录和日志全部保留，不把它改成通过。

## 原始证据和科学边界

服务器报告：`/HUBU-AI096/zp/ICML/stage04_finish_38e6a44/results/run01/environment_preflight_11/preflight.json`，SHA-256=`901110a227de747596d3acfd8bdc4c853c242b00b311dd902b12f371ba9eaaf0`。

服务器日志：`/HUBU-AI096/zp/ICML/stage04_finish_38e6a44/logs/run01/01_preflight_11.log`，SHA-256=`06e1662cc6241a8818772fc7356adbf67386ab133e42846d335ce46b2eabcc9e`。

本地已核相同SHA副本：`/Users/zhangpeng/Desktop/Learning_Not_to_Act /reports/stage04_preflight_review_2026-10-14/evidence/`，另含实际安装源码及CPU fake reproducer。冻结194源码和10部署文件复核一致，不能把此错解释为用户改环境或命令。

这条是技术错误，不是0%模型成功率、不算有效保持测量，也不支持“原模型不能处理已完成任务”的结论。release和hold正确性仍未知。HDF来源映射0/50的独立前置问题仍按[准备记录](../../docs/stage_summaries/stage04_data_preparation_2026-10-14.md)处理，本修复不自动解决数据分组、不允许直接训练。

007与本review保持开放，不删除历史交流／失败证据。下一步：X修最小兼容性错误并交CPU证据；Codex审查部署；用户按新命令重新启动预检。
