# Stage04：008两域软件验收、部署与真实audit起跑点

日期：2026-10-15。范围：代码审查、冻结部署、CPU/fake与纯文件准备。**008 accepted（软件），未closed；Stage04研究未closed。**

## 已完成

[PR #5](https://github.com/No1dry/LIBERO-Remain/pull/5)将用户批准的两来源域方案落实到audit/cache/head/parity/job/calibration全部消费者。[正式裁决](../../collaboration/reviews/008_round1.md)：无明确阻塞，不要求本轮返修。

- 008 base/007合并main：`94c061e99168d76fbe50bef85b187db8fe2b9898`。
- 008已测试实现：`b973133a08216eaab4a36901b1b968c4d8b87452`。
- 冻结交付/部署：`b596af26e167450beb7f3c7fe61b6dfd53523ef6`，tree `d2e4d3571d91733df5d4106a67061653879ab119`。
- 本地393 FINISH全过；全套1624 passed / 12既有可选skip。服务器393 passed / 0 skipped，57.01秒。
- 并行独立tiny/fake数据83项、消费者166项通过；21条runbook调用只做真实parser核对。
- 220个源码文件与GitHub Git blob/SHA-256一致，9个私有部署文件冻结。原environment/runner/schema/metrics/evidence/oft文件与已验4f版本逐blob相同。
- SSH一度拒绝，用户恢复后成功连接；只上传全新目录，不触碰原脏checkout、原实验或依赖/权重。

## 已部署与文件证据

源码：`/HUBU-AI096/zp/ICML/LIBERO-Remain-stage04-finish-b596af2`。
会话/配置/结果根：`/HUBU-AI096/zp/ICML/stage04_finish_b596af2`。

纯文件budget、plan-data、register-data三个阶段均command_exit=0且tee_exit=0，没有创建仿真、恢复状态、生成label或加载VLA。registry registered_file_only、labels_generated=0、ready_for_feature_export=false。

| 域/角色 | 实际文件注册 |
|---|---|
| HDF head_train | 30轨迹，预定1115采样帧 |
| HDF head_validation | 5轨迹，预定198采样帧 |
| HDF head_unused | 15轨迹，0恢复/采样任务 |
| init normal_calibration | 35..39，5来源 |
| init normal_test | 40..49，10来源 |
| init Remain | 0..4，5来源；后续10/01/11共15案例 |

下一真实audit预定1313次当前帧恢复；全满且已释放的帧再独立同状态K4 hold，其数量由物理truth决定，不预造标签。198个head_validation候选不等于32个实际模型输入已通过去重/parity。所有真实阶段仍未开始，模型30条rollout预算未消耗。

关键hash：

- GitHub源码tar：`a1179d9d7352d78660475b1186cee8f72cdf3d27d801059cb9866314d0758691`。
- 私有部署tar：`95a8e78902d4ce2b0f84ce2790b6652c46f3de28ea2601dca79c4944a4e85297`。
- 私有配置manifest：`a3f579cf226a3775b3a4670c6155437622dc41962aa1b3f070ebb7c98552ba04`。
- OFT runtime原字节：`75f2a711a39c58a07715b3a280aeba26a29dfbba70caf87cc051520f0a3f9720`；只复用，未更换crop/seed/chunk/checkpoint/patch。
- registry语义SHA：`f8706e9018e618566f53165b50b8e21e6347c089a500cbe3bc21c0930ff8edfe`。
- registry文件SHA：`18491d64d5bcc6dfef18dd97f8191aabb1577e111216d0e566a2ee8b1cd15581`。
- server JUnit SHA：`a875dc13a638447ebe2c94b6562559cd49b6a4b09ef511f67a1f1ee4be9829db`。

本地证据在项目`reports/stage04_pr5_review_2026-10-15/`，含源码/配置清单、两份本地JUnit、服务器JUnit/plan/registry/3份日志与deployment_receipt.json；六份服务器证据已下载且逐文件SHA一致。后续总结/审查/实际命令按README另备份到research_archive/LIBERO-Remain并登记来源commit。

## 未完成与不能声称

没有真实audit标签、feature、head训练、parity、阈值校准、normal/Remain新eval或新视频。本轮不是停止能力成功率。4f的单11四步预检已通过且不重复，但不代表W150或夹持负例已认证。

两域保证明确整轨迹分组和不直接训练编辑评测输入；HDF与eval init的物理祖源独立性仍unproven，冻结SOG10是否见过eval来源也未证明。成功示范不覆盖失败/停滞负例的限制保留。不为压低baseline改分组/阈值。

## 下一步与协作闭环

[已填实际路径的逐阶段启动手册](../experiment_plans/stage04_task008_server_runbook_2026-10-15.md)。用户先启动唯一真实audit；Codex读取1313帧的完成性、两类标签/unknown/身份和物理计数，数据充分再交feature/训练。禁止自动串联。没有额外新预检、重下载或新采集门槛。

X可按验收保持实现及最新协议文档合并PR并登记，不由Codex代合并；冻结代码无需等待合并才运行。效果差不是返修理由，有明确错误才给具体证据。

本轮交流清单：task008、response008_round1、review008_round1；007历史审查/失败/成功仍需追踪，008未closed。**精确待删清单=[]**，没有删除、重写历史raw或缩减分母；已部署旧38/4f、stage03数据/视频、HDF与用户工作区全部保留。
