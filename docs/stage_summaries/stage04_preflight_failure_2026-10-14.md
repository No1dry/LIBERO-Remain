# Stage04 首次真实preflight：技术错误与下一步

2026-10-14，Codex。用户亲自启动，Codex只读审查和CPU-fake复现，没有代启动／重跑真实环境。

## 结果

冻结源码38e6a44，source001的basket_s000_11。用户日志UTC06:56，Asia/Shanghai14:56。命令完成，但不是通过：command_exit=2／tee_exit=0，status=technical_error，error为unsupported Panda/gripper incremental-action contract。

trace=[]，model_calls=0，初始观测artifact／hold_contract都未写出。真实启动进入reset后的机器人合同检查即失败，没有任何请求的4步hold测量或VLA rollout。**不是模型失败／0%成功率，不拿技术错误当研究现象。**

## 确认原因

固定LIBERO8f1084的living-room task把Panda映射为OnTheGroundPanda（ManipulatorModel，使用Panda XML和PandaGripper）；FINISH environment._robot_contract第75–78行却要求robot_model类名严格等于Panda，所以误拒绝这个已在范围内的官方任务。

已读当前安装源码而非导入／实例化环境；有效robosuite1.4.0的PandaGripper仍dof1、speed0.01、current_action2维，0增量命令保留原finger目标。检查有效OSC代码后未发现另一项静态可确证的接口不兼容；不因此宣称真实hold稳定。

CPU fake只变robot_model名称即可复现Panda通过／OnTheGroundPanda拒绝；没有修改X实现。之前R1只覆盖Panda fake，Codex的软件审查遗漏此真实类型。R1通过的237／全套测试是历史软件证据，不能当真物理通过。

## 裁决与最小下一步

task007由历史软件accepted进入**changes_requested（一个P1机器人类型兼容性错误）**；PR #4仍open，暂停未修版发布／全部受影响真实FINISH阶段。详见[007_round2](../../collaboration/reviews/007_round2.md)。

X修受支持类型识别并加CPU回归，保留全部夹爪／controller安全合同，不以宽泛Panda字符串、简单isinstance(Panda)、升级环境、改GT停车或放宽H/W解决。可增加具体拒绝字段日志作为建议，不因偏好返修。

X交付新SHA与测试后Codex审查、部署到新目录，提供新日志/out命令；用户再启动同一个source0_11预检。当前不发布旧命令让用户原地重跑。来源映射的另一个前置问题尚未建立，兼容性修复不自动让head可训练。

## 证据与保存

服务器失败报告和日志保留在`/HUBU-AI096/zp/ICML/stage04_finish_38e6a44/results/run01/environment_preflight_11/`和`logs/run01/01_preflight_11.log`；本地已备份到`/Users/zhangpeng/Desktop/Learning_Not_to_Act /reports/stage04_preflight_review_2026-10-14/evidence/`。

| 文件 | SHA-256 |
|---|---|
| preflight.json | `901110a227de747596d3acfd8bdc4c853c242b00b311dd902b12f371ba9eaaf0` |
| 01_preflight_11.log | `06e1662cc6241a8818772fc7356adbf67386ab133e42846d335ce46b2eabcc9e` |
| 服务器living-room任务源码 | `a13bc0a92ff746d572a6d76e09add98dafad70d88928555068728641c6c9de10` |
| 服务器OnTheGroundPanda源码 | `7d580aeee632e164f327cf6b1951861bec40cf814cdbe92bcfc469a93e1f9fa8` |

194个部署源码／10个部署文件核验一致，runtime／模型／source／split未修改，失败不是身份漂移。Stage03历史raw和视频不改；本次没有新模型成绩，Stage04未closed。

交流tasks/007、responses/007_round1、reviews/007_round1与007_round2均保留，其他未闭环事项也保留。**待删清单为空**，没有删除任何文件。总结提交GitHub并本地核对来源commit与SHA后登记backup_manifest；之前数据准备／软件验收总结不倒改。

下一步操作：X修明确兼容性错误；Codex审查与部署新冻结版本；用户启动同一11预检。执行者依次为X、Codex、用户。
