# Task033 R7位姿稳定软件验收与隔离部署

日期：2026-11-02。用户已确认的来源准入修订完成软件交付/审查/部署，真实微波炉仍待用户启动；不是物理来源或模型成功结果。

## 裁决

**accepted，限R7软件、既有证据文件检查及隔离部署；无阻断返修。** 新物理规则尚无本轮真实结果，当前仍20/30=66.67%来源ready，新三30条模型未开始，不能从CPU/fake推断物理修复成功。用户可直接启动本次必要补建，不必等X再确认。

独立stability_profile=active-free-object-pose-stability-v7与原RGB observation_profile=v6分离。A杯子完整150步/151观测按位置bbox跨度≤5mm、归一化四元数最大两两最短旋转≤1°；q/−q等价，原state/qvel不改，A速度只诊断，非A速度仍0.01。完整joint/layout/模型XML绑定由实际模型解析，构造及正式恢复核对，避免错误豁免其他坐标。

原全场景位置、穿透/机器人/reference、native10/Open、RGB v6/非RGB初态精确与动态1e-8、非步进state位模式及hash要求、150构造+分别恢复的150/150均保持。static0不能授予source ready，缺151点/第二回放、错误映射或跨profile证据仍拒绝。新schema/reader显式分支，旧v4/v6/证书/失败解释保留；冻结06817e61不读新v7，不热改。

复用R5几何、24候选、base80、min80/max400及原操作账本/首0门控。固定0真ready才派发1..9，失败即停、缺子证据保留unknown；不自动retry或部分20评测。旧20各自原profile复用，不声称已有新姿态认证。任务/模型/输入/评分未改，物理GT只用于来源准入和计分，不向策略增加输入。

## 独立软件证据

仅运行本轮四个新R7测试文件：**95 passed，0 skip，10.01秒**。覆盖数值/姿态、producer/实际ReplayAuditEnv软件链、reader/归档及队列；native IO为fake，不冒称610控制调用是实际物理样本。X的153项受影响原回归作为交付证据复用，不重复历史53/234/280全组。

JUnit SHA256 `94409bed5ae95b8e7ba6a963b6420c0d473ac09df739c65598af0d263979129b`。源码归档SHA `c26dde388007b6dd38dbc14ae38b5266604a5c25ab4b3d395ae2ed680cc4bf8b`。

## 服务器部署与执行边界

隔离代码：`/HUBU-AI096/zp/ICML/LIBERO-Remain-task033-r7-d8541ef4`；新输出根：`/HUBU-AI096/zp/ICML/task033_r7_d8541ef4`。旧aedfe169/06817e61/942db12f源码和数据均不改。

归档SHA与本地一致，五个受影响实现文件SHA逐个一致；原R3报告/源清单及R5真实失败报告按固定SHA绑定。服务器纯文件_inputs复验20个旧ready及其证书、reviewed_revision核验20ready/1failed/9not_attempted和相同旧20引用。两个固定真实XML同SHA；文件检查23.56秒。没有创建仿真、restore/step、模型或训练，用户microwave_repair输出尚未创建。

[完整用户python命令](../../docs/experiment_plans/2026-11-02_task033_r7_server_commands.md)已发布、本地备份。此次是明确披露的来源测量修订，不把旧9600 settle点补成证书，不根据VLA成败挑来源；准入版本需在新增30模型评测前冻结。

下一步用户启动必要真实构造与两个回放，Codex读回实际报告；只有30个新增来源全部ready，才给一次新增30条10模型命令。00完整78/90=86.67%、旧六10六十条/旧20来源复用，不重跑，不partial20、不allow-missing、不自动串联eval。X本轮无返修，033整体open，PR不自动merge、不清理，待删=[]。


## 长期证据与未完成事项

固定交付HEAD d8541ef4，实现c8c50e63；X回复responses/033_round7.md。本地reports/task033_r7_review_2026-11-02保留原源码归档、95项JUnit、部署脚本/服务器receipt、实际运行命令。总结、R8审查、命令、X回复同步到research_archive/LIBERO-Remain，backup_manifest记录来源commit及SHA。

软件准入规则与GPU策略效果必须区分：新三来源当前仍20/30 ready，旧R5真实首源仍failed、其余9该次未尝试；新v7不追认旧日志为ready。新profile须用新的完整原state/接触/观察与真实151点构造+独立回放验证，0号失败即停，不改更多阈值/等待预算。新三30模型未启动，旧六60/90模型覆盖与准备百分比分开。

旧00完整90/官方78成功仍复用，原20各自旧profile有效，不声称已做新姿态认证；旧源码/数据/失败不改。033整体仍open；旧任务/回复/审查均保留，精确待删=[]。下一步用户亲自启动必要补建，Codex读取真实报告；齐30后一次评30，不partial20/allow-missing，不训练FINISH/030、不自动merge或启动实验。
