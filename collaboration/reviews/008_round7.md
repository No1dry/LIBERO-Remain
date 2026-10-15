# Codex：008 Round 7——已核示范模型变体的软件验收

日期：2026-10-16。裁决：**accepted（R6受限兼容实现），无进一步返修；008/Stage04未closed**。

[PR #5](https://github.com/No1dry/LIBERO-Remain/pull/5)已测试实现b26497959839f79d2d5f2790c2da95d949347102；最终冻结2cb1428f312175968ac42449994c219e94e9ab14，tree ad11cec8a6cec508969c11b84efef61bf1f64581。实现到最终head只有STATUS/response文档，250源码文件逐Git blob/SHA-256核验。保留最新main12c67c8和R1..R6全部裁决/诊断。

## 本轮确认

- 只在DemonstrationAuditProvider接受源文件实际SHA/profile/50XML成员/资源扫描完全绑定的已知变体，无任意allow_mismatch。exact默认路径保留。
- 固定已核基准layout canonical SHA与真实诊断一致；仅第73位恰好一个robot0_link7_collision插入，比较副本排除后完整剩余layout精确相同，7个匿名geom及顺序未丢，关节地址无重映射。
- 新增geom的实际body/type/mesh、完整资源suffix与已核SHA、接触属性、匿名几何及两policy相机继续核验。原XML/geom不编辑、不删除、不禁碰撞，不声称物理等价。
- 当前task/robot/controller的sim引用和全部object/fixture body ID必须指向新model；只检查、不额外setup/reset/step。接口与固定LIBERO/robosuite实现吻合。
- provider最终动态metadata及具体错误证据进入audit SHA，沿原cache/head身份继承；close/metadata/source/asset错误仍撤ready、保留partial；没有metadata进policy。
- 唯一生产变化为finish/demo_model.py、environment.py、data.py。Codex AST确认_robot_contract/PandaPoseHold/_release/BasketContract/FinishLiberoEnv/_layout/_processed_demo_xml以及provider原恢复/truth/hold/close关键方法不变；原分组/label/K4/H520/W150/chunk/网络/阈值/评分与eval/source001均不改。

## 独立CPU/fake证据

| 检查 | 实际结果 |
|---|---|
| 本地全套 | 1766 passed / 12既有可选skip，55.56秒，共1778项 |
| 本地新增3文件 | 78 passed / 0 skipped，3.24秒 |
| 并行来源/metadata审查 | 87 passed，4.17秒 |
| 并行模型/provider审查 | 135 passed，3.17秒 |
| 服务器22个FINISH文件 | 535 passed / 0 skipped，70.51秒 |

12 skip为11个缺可选固定源码的catalog检查、1个缺imageio_ffmpeg，与X Windows15个平台/可选skip差异一致，无新增skip。本地JUnit SHA：全套863be79681fafb0a011e9e6254e364657e64c878a6714a002772aa15cc48dcbe；新增b461e860a37ae5aca2c19b36de759154dd0307acf4c68ed3e2055bfc546077cb。

## 部署与范围

新源码/新会话已部署，250源码/9部署文件冻结；真实HDF register-data全50 XML/4450引用/87路径、errors0，仍file-only非ready。实际固定source/baseline/mesh身份核验和证据详见[长期总结](../../docs/stage_summaries/stage04_task008_model_fix_acceptance_2026-10-16.md)，[新会话完整命令](../../docs/experiment_plans/stage04_task008_model_server_runbook_2026-10-16.md)。

本轮仅CPU/fake、纯文件准备与既有布局JSON回放，没有新native场景、HDF恢复、物理label、VLA/feature/train/parity/eval；上一次有限布局诊断授权不自动扩大。**软件受限规则通过不等于新真实audit通过，也不保证0/1覆盖或stop能力建立。** head示范模型与eval模型差异、原机资产字节与跨域祖源未证明等限制保留。

解除R6实现合并暂停：X可保持已审实现及最新README/Plan4/STATUS/R1..R7与原始证据，合并PR并登记merge SHA；Codex不代合并，冻结实验版本不因合并漂移。旧b596/9ddd/089失败和38/4f历史全保留。

下一步：用户用新2cb1428会话只重跑同一1313帧audit；Codex读实际0/1/unknown/身份/兼容证据，充分后直接feature/训练，不新增独立预检/下载/采集。任务与研究未closed，精确待删=[]。
