# Stage04：释放审计提案接受与009最小诊断授权

2026-10-16。X回复008_round6已审阅，HEAD54364ebb579d38a81d2d9396585d084cb9ac21da相对3433f48无生产变更；提案accepted，不要求文档返修。原5条shadow完整但校准未建立／selected_threshold=null的结论不动，也不撤销R9及此前audit/features/head/parity/bank验收。

用户已明确同意：“同意最小诊断”——X实现独立入口，仅35号原初态顺序重执行最多292条已记录动作，不调用VLA／FINISH头、不改原判据或分数；代码验收后仍由用户亲自启动。没有授权Codex跑native，没有授权协议修改、重训、升级依赖或追加其他数据。

## 新只读核对

Codex核对3350动作／trace关联、330 query、6710个target release规则和3355顶层聚合，分支不一致0；这证明旧输出忠实遵循旧规则，不证明unknown已物理释放。索引明确35首hit为step280/query36／视频14秒附近；未声称目视检查原视频。

None两端假设补全得到紧确tau：35[263,292]，37[287,295]，38[241,250]，39[364,380]，36无参考。后三条首次hit296/256/384的timely对全部补全稳健；35仍不稳健。X条件性外包界可收紧，不影响提案结论，也不是新的实现返修理由。所有补全仅分析，不替代标签或作为新阈值。

服务器metadata/header确认MuJoCo2.3.7、robosuite1.4.0；固定header无mj_geomDistance，存在mj_stateSize/getState/setState/contactForce，integration mask含FULLPHYSICS/USER/WARMSTART。仅读文件、未创建模型／native实例，实际native记录仍待用户作业。API及contact受margin/过滤约束的边界已核[官方2.3.7文档](https://mujoco.readthedocs.io/en/2.3.7/computation.html#collision-detection)。本轮未加载研究头/VLA、未做sim或训练。

[机器证据](evidence/stage04_release_proposal_review_2026-10-16.json)保存原校准身份、每条界限与动作计数、授权范围和限制；本地reports/stage04_release_proposal_review_2026-10-16保存原X回复、纯文件脚本与结果。原视频／inputs树未因此复制或改写。

## 决策与下一步

[008 R11裁决](../../collaboration/reviews/008_round11.md)及[009完整任务](../../collaboration/tasks/009_release_observability_replay.md)已提交。第一版只做sidecar证据记录／旧规则对照，避免同时研发新几何判据和协议重构。新诊断计划/结果与原工件分开、mismatch即停；292控制步不隐藏初始化/内部substep，不误称恢复原280快照，不补FINISH或W150，不把诊断写成任务成功率。

X先实现及CPU/fake，交PR/实际命令；Codex再审查部署、用户启动。PR #5已审部分可按R9由X合入保留最新main文档；009独立PR，Codex不代合并。首个诊断之后才讨论证据支持什么及是否另需协议变更，不能以本次是否过0.99来选规则。当前normal_active/Remain仍暂停，用户现在无新实验命令可启动，不重复已有阶段。

分工与清理照README：原DeepSeek历史保留，不分配新任务；原实验／失败partial／脏工作区不改，无原数据删除。008/009/Stage04未closed，精确待删=[]。本总结／R11／009／证据／STATUS及X回复本地备份来源commit+SHA核验。
