# Stage04：首次两域真实audit在provider初始化失败

2026-10-15。用户运行了b596af2冻结版本的03_audit；Codex只读取结果、实际安装源码、做CPU fake定位与归档，没有启动真实实验。

实际结果：status=insufficient、command_exit=2/tee_exit=0；ValueError invalid Panda current_action；provider_identity为空，采样restore_attempts=0、rows=0、hold_attempts=0，尚未生成标签或运行VLA。不能把它报成训练数据类别不足或模型0%成功率。R1的393项FINISH与全套1624通过仍是软件证据，不等于真实audit通过。

根因是原007已有provider生命周期没有被真实单11预检或008替代provider测试覆盖：robosuite Panda刚reset的current_action为shape(1,)，而provider在原状态恢复同步之前两处提前构造严格shape(2,)的BasketContract。正确的既有restore_raw_state会从实际finger qpos同步两执行器目标；预检走这一正确顺序，所以先前4f成功不能证明audit路径。具体位置、两处一起修及CPU回归见[008 R2](../../collaboration/reviews/008_round2.md)。不为放行训练降低物理标签标准。

代码冻结仍b596af26e167450beb7f3c7fe61b6dfd53523ef6；PR #5保持open，本P1修复验收前不合并/重跑。两域设计与原R1数据域审查保留，当前真实运行被明确故障阻塞，不要求研究方案返工。

服务器原始证据：

- `/HUBU-AI096/zp/ICML/stage04_finish_b596af2/results/run01/audit/audit.json`，文件SHA `d9b6e03249a3a0efdbdbb17a25af21d5614023f51ffe2b5fb1c443243db486ee`，内部audit_sha256 `b64426a02c2691ad4476fc052f8a33678f59ca23e0bcd7bddad4c1031d7a8675`。
- `/HUBU-AI096/zp/ICML/stage04_finish_b596af2/logs/run01/03_audit.log`，SHA `68de946734df6f3b705023fabf960069dab9e58206a35a781d8184582e75c573`。
- 已下载项目`reports/stage04_task008_audit_failure_2026-10-15/evidence/`并逐SHA核对一致。初始化可能已经创建/重置环境，但没有进入采样循环，不能把restore_attempts=0说成没有任何环境构造。

范围不变：同一1313采样帧、两域/原模型/label/K4/H520/W150/chunk8；不新增预检、数据采集或下载，不把unknown/空标签改成训练输入。X修最小生命周期错误并补真实provider类的CPU fake；Codex审查部署后用户在新目录重跑同一audit。通过后才给feature/训练命令。数据不足/效果差与软件错误分别处理，不为了压低baseline改协议。

Codex此前把软件通过表述得过于乐观，本记录明确收窄：尚无真实可用训练cache/head/parity/calibration/eval或新视频。停止能力和外部部分完成现象尚未得到Plan4模型结果。

007/008及Stage04未closed。本轮开放交流：task008、response008_round1、review008_round1与新review008_round2；无删除，精确待删清单=[]。失败raw与旧38/4f成功/失败全部保留，总结/审查/STATUS提交后本地按README来源commit和SHA备份。
