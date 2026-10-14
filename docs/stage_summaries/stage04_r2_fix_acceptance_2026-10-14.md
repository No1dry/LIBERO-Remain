# Stage04 R2机器人兼容性修复验收与新部署

2026-10-14，Codex。小阶段完成：P1软件修复accepted并部署；不是Stage04科研完结，也不把CPU软件验证写成真实物理通过。

## 问题与修复

旧38版用户11预检在reset后误拒LIBERO OnTheGroundPanda，trace为空、model0、exit2。X在a7dda8d中精确识别两个已验证qualified robot类型，保留全部PandaGripper/OSC检查、当前pose/finger目标保持与gripper0；增加固定源码AST／非物理fixture回归，完整证明官方类并非Panda子类。没有改控制公式、GT停车、H520/W150/chunk8、camera、权重、依赖、source/split或指标。

当前交付head4f76f4917a9174fc5b80ef83e3cf21eaf053c98d与测试实现仅STATUS和回应文档不同。Codex裁决accepted（软件P1修复），无返修；详见[007_round3](../../collaboration/reviews/007_round3.md)。PR #4仍由X按既有授权处理，Codex不代合并，007不标closed。

## 独立验证

本地10个FINISH测试261 passed/0 skipped、8.06秒；全套1492 passed/12个已解释skip、30.69秒，共1504。服务器新部署261 passed/0 skipped、23.17秒。并行交叉复核68 passed。fixture字节与服务器固定源文件一致，204个GitHub blob与部署后源码一致。全部CPU/fake，没有本轮真实sim、restore、hold、VLA、真实数据训练。

JUnit、源代码核验和具体安全合同复核在review及本地`reports/stage04_r2_fix_review_2026-10-14/`。保留旧dirty工作区，未pull/reset。

## 新部署身份

新源码快照：`/HUBU-AI096/zp/ICML/LIBERO-Remain-stage04-finish-4f76f49`；新运行根：`/HUBU-AI096/zp/ICML/stage04_finish_4f76f49`。源码无.git，逐文件inventory核验，不在其中git pull。

| 产物 | SHA-256 |
|---|---|
| 固定源码归档 | `3fa1700b67320f653d933b074919b601e95b0192a34af8020b2851eed4eee3ac` |
| 部署配置归档 | `63647d100819b770749d09c549c50ccd26efbfc2baec45d242baac1b48281d67` |
| source_inventory.json（204文件） | `f1e33307acab99bd443cfcfe7228d3a9cd9a9460bc0292ac040b73f67313da0c` |
| configuration_manifest.json（4文件） | `76e67949c313510fc23e78ac32ca5fe4d76d64bdd120b3ff0aee38bb2d59f4ef` |
| 服务器FINISH JUnit | `0198e7f616bb31d7e60b974b5b1908182a7205c0bfeb719b717e1ca6224f2968` |

4个冻结部署文件是preflight_source、session、verify_deployment、source_inventory，仅为同一11预检配置。复用原sim runtime／源包／replay，没有复制或重新生成场景，也没有升级依赖或替换权重。旧38版和失败SHA全部保留。

## 下一步与尚未验证

用户按[新单预检命令](../experiment_plans/stage04_preflight_r2_runbook_2026-10-14.md)启动同一basket_s000_11，输出`results/run01/environment_preflight_11_r2`；Codex读取真实hold／release／unknown证据。源码类名错误已软件解决，不保证真实pose保持、几何释放或W150覆盖通过。

HDF来源精确对应仍0/50，独立数据分组前置问题未解决；当前不跑audit／feature／训练／新eval。默认30个模型rollout尚未消耗，没有新成功率或paper现象结论。

角色仍为用户启动真实实验、Codex准备／审查部署、X代码实现。交流007任务、R1/R2回应、R1/R2/R3审查均保留；P1软件修复有裁决，但007和真实研究阶段未closed，**待删清单为空**。本总结提交GitHub并本地backup_manifest记录来源commit与SHA核验，不倒改历史失败或清理开放事项。
