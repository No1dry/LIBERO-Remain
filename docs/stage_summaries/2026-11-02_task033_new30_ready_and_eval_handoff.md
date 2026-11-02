# 新三任务30个10初态真实就绪，进入完整模型评测

日期：2026-11-02。来源准备已完成；真实VLA新增评测尚待用户启动。

## 裁决与结果

**accepted，限新增三任务30个10来源准备与本次文件配置。** 新来源30/30 ready（100%），微波炉10个各完整150构造＋分别恢复的150/150回放通过；每源实际610控制调用（80base+80settle+150audit+300replay），合计6100。抽屉10、双壶10原样复用，不重建。旧失败和各profile解释保留，没有将R5的9600采样点改写成证书。

本次来源报告policy_called=false、model_rollouts=0，准备100%不是VLA成功率。R7位姿准入使这批来源可进入评测，不是模型能力改进的证据。ready行中可能保留早期missing reason字符串，但已完成操作/最新状态和完整reader证据一致；不为该历史文案返修或重跑。

## 文件配置完成，可直接开跑

Codex只执行configure和dry-plan，均exit0（13.28秒/52.66秒），没有创建仿真或加载模型。实际正式reader核对全部新30来源，selected30/ready30、expected90、旧六reuse_only60、runtime_errors=[]。完整三任务各10条固定index0..9，没有allow-missing、换index或额外probe。

- 配置：/HUBU-AI096/zp/ICML/task033_r7_d8541ef4/configs/mask10-new3.json；SHA 615bedc85b59a8c3cab5fecdea1eb9d1780bab25a530b93554ae02c193751094。
- runtime与原配置逐字节相同；SHA bff0f6f0247e4794040322ebe9c4c229586bb596640188b9ec8241cba06777f8；保留原独立OFT worker venv别名。
- 完整plan SHA c7092652d08f3dfcd6a645bf6648a04a763f3ea25f1929fee1801a3eb1721fa3。
- 来源报告SHA bf321a1169da6b7251caa2db7aa2cccb45f650adea4f83aa2b76dbe1b852f906；sources SHA 6c4187bd695fca6e149174fc931d76e4c1dbf7e98d94de33d1ec0d599939e189。

[用户正式模型命令](../../docs/experiment_plans/2026-11-02_task033_new30_mask10_eval_commands.md)。此时不再追加构造、回放、测试、warmup或模型probe，也不要求X再改代码或确认后才允许启动。代码路径含r7只是固定版本名，此run入口执行的是模型评测，不是来源准备。

原官方OpenVLA-OFT SOG10 checkpoint/statistics、全精度、crop/proprio、seed7/chunk8/H520、原始完整指令与10目标终点/违规计分不变，无FINISH/selector。只执行task3/8/9各10，旧六60条10只读复用，模型记录覆盖当前仍60/90=66.67%，新增30仍0%。00九任务90/官方78成功原样保留。此次30完成后，summary自动合并旧60生成九任务90条10报告，并保存逐条完整视频。

新输出runs/mask10-new3-001尚未创建，Codex没有启动/排队/监督模型、仿真或训练。用户现在可启动单次30条正式评测。033整体尚未closed，X无本轮实现待办，不自动merge/清理，待删=[]。


## 当前阶段结论与备份边界

本轮通过的是来源准入/可运行性，不是模型SR，不提前为研究假设下结论。R7的A位姿稳定规则是已披露的事后来源测量修订，RGB v6/其他物理门槛和模型任务评分未改；旧20按各自旧profile复用，微波炉10新profile真构造/回放结果独立保留。旧R3/R5失败不追认成功、不删除。

真实完整native原工件仍保存在服务器microwave_repair/preparation/attempts/，不会因进入eval删除。此次本地阶段备份的metadata归档仅包含总报告、源清单、固定配置、完整文件plan和receipt；不是已搬回全部native原始图像/状态的声称。后续原视频随真实模型run生成，完成后按需取回。

本地reports/task033_r7_results_2026-11-02保存文件准备脚本、真实文件receipt及正式命令；总结/审查/命令同步GitHub与research_archive，backup_manifest记录来源commit和SHA。原模型/代码/数据脏工作区与未合并交流保留，不自动merge，不清理，精确待删=[]。
