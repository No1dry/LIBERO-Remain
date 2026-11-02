# Task033 R5软件验收与仅微波炉部署

日期：2026-11-02。本阶段完成代码审查/CPU-fake与部署，真实微波炉仍待用户启动，不是完成30来源或模型评测。

## 裁决与范围

**accepted，限R5软件、旧证据文件检查及隔离部署，无阻断返修。** 用户现在可启动微波炉10来源准备，不必等待X另一次确认。真实来源仍是20/30=66.67% ready，微波炉0/10；不能把本轮CPU/fake或静态几何通过写成物理修复成功。新三30条10模型仍未启动，033整体open。

新方法 `microwave_gravity_support_pose_transplant_v3`只允许nine-mask10/mug_microwave_close与显式v6。四种重力对齐yaw对真实39个杯子collision box重算角点/完整footprint、底高、有限底板、原有向容积及墙/开门余量。只改A的7个种子qpos，保留全基底qvel和其他分量，落稳后移植测得实际pose/quat/qvel；没有把门关上求通过、改资产/solver或修改官方谓词。

R2的24候选、base80、候选min80/max400、连续20帧/qvel0.01、150构造与独立paired300、位置/穿透/机器人、RGB v6和非RGB要求都未放宽。几何AABB是保守候选过滤，可能漏掉可行种子，也不证明接触稳定；最终真实审计仍是准入依据，此风险non-blocking，不额外要求标定/模型probe。

窄入口绑定R3报告/sources原SHA，原20引用和证书复用，输出隔离；先固定index0，只有构造+两个回放实际ready才派发1..9。0号失败或派发后缺证据即停，保留not_attempted/interrupted及unknown计数，不重试已尝试来源。无额外模型episode，不按结果换index。

## 独立验证

本轮新三测试文件及12个受影响原回归合计**45 passed，0 skip，3.10秒**。包括33项R5测试与12项旧回归，不重复跑53/234/280全组。专用bare对象缓存仅取得固定06817e61；旧reader测试通过git archive原commit、python -I隔离读取：新v6工件ready、归档/快照复验通过，缺第二回放审计被拒绝。未热改旧reader或用户脏工作区。

JUnit SHA256 `c1aada34265c700ce3d3a04141e726ad81f059742b52310ba0cda1f22fbd273f`。
部署归档SHA256 `f908a9c1630e1e90c5a6ad60379ea563122acf3dfaf6afc7d08f74499d4b144a`。

## 实际部署及文件检查

- 代码：`/HUBU-AI096/zp/ICML/LIBERO-Remain-task033-r5-942db12f`。
- 输出根：`/HUBU-AI096/zp/ICML/task033_r5_942db12f`；仅已建logs/部署receipt，用户的microwave_repair输出尚未创建。
- 原仿真venv路径保留，未解析成底层conda解释器，未升级依赖。
- 服务器归档与本地同SHA；四个部署实现文件SHA逐个与本地一致。
- `repair033_microwave._inputs`仅文件检查，20条ready原引用及证书全部通过，原报告/源清单SHA未变化；两个真实XML与测试对应的固定资产SHA完全相同。22.09秒，无仿真编译/restore/step、模型或训练。
- 无native动作/新模型轨迹，旧R3失败及原始数据未覆盖。

[用户完整python命令](../../docs/experiment_plans/2026-11-02_task033_r5_server_commands.md)已发布，并本地备份。用户已选择等30齐备后一次评30，不给部分20或allow-missing命令；补建不会自动串联eval。0号仍失败就交回证据，不重复盲跑剩9。X本轮无返修待办，勿修改冻结部署或自动merge；PR与交流保留，精确待删=[]。


## 长期归档与当前未完成项

X交付：responses/033_round5.md；R5新实现fc2dd617，固定交付HEAD942db12f。原033 R5工单、R5回复、R6审查均因033仍open而保留；不自动merge或清理。

本地 `reports/task033_r5_review_2026-11-02/` 保存固定源码归档、45项JUnit、部署脚本/服务器receipt、实际命令；总结/审查/命令/X回复复制至 `research_archive/LIBERO-Remain/` 并以backup_manifest记录来源commit和SHA。服务器SCP首次连接中断，第二次上传成功且按完整归档SHA验收；没有据中断传输宣称部署成功。

已有真实20个初态（抽屉/双壶各10）保留，微波炉10未获得新物理结果；新三30个模型episode尚未启动，九任务10模型记录覆盖仍60/90=66.67%。00完整90条、官方78/90=86.67%不重跑；不启动部分20，不扩任务，不训练FINISH或030，不把准备失败写成VLA失败。下一步用户按独立命令启动必要微波炉准备；Codex读取真实结果后才给一次新增30条10模型命令。
