# 033 R5｜微波炉10构造修复交付

日期：2026-11-02；身份：X。沿用 [PR #14](https://github.com/No1dry/LIBERO-Remain/pull/14)，本轮实现commit `fc2dd617b9434a82d27710d1da023101e87af1f5`。先fetch main到 `fcfc7beaa47d61ab0872e0295293d12f57ca4d57`，阅读R5工单、审查和精简原始读数后合入，实施基线 `0b3e37152e600cddaa08642d6c3dd097d1bd0359`。没有修改冻结 `aedfe169`、`06817e61` 或旧结果。

## 结论与证据边界

已完成微波炉专用几何/姿态构造、首源门控和旧20来源复用接线，待Codex审查部署。新增33项CPU/fake通过，受影响旧回归12项通过；独立代码复核未发现阻断。没有启动真实仿真、回放、模型、训练或自动合并。**真实微波炉仍是原记录0/10 ready；本轮不宣称10个失败已物理修复。**

原读数确认240个候选全部400 HOLD后未收敛，96,000候选样本、微波炉96,800实际控制步；最长连续合格13而需20。部分读数微小位姿摆动不能替代qvel/150/回放通过。直接阻塞是稳定性判据，接触成因仍未证实；本实现把承托与姿态作为可验证改进假设，没有把它写成已经证明的根因。读取了仓库精简读数与本地固定XML，没有声称本轮重新下载/逐条读取了服务器全部raw。

## 改动

新增 `microwave_candidates.py`，仅供显式 `microwave_gravity_support_pose_transplant_v3` 使用。只接受 `nine-mask10/mug_microwave_close/index0..9` 和v6，非法任务/条件/profile在创建输出、导入backend前拒绝。R2抽屉、R2旧微波炉路径及通用 `construction.py` 未改。

1. **真实有限承托面。** 确认实际底板local pos `[-.04,-.004,.012]`、half-size `[.1035,.084,.012]`，只允许这个固定collision box，不用墙帽/屋顶替代。完整杯子footprint必须落在底板上，同时满足原有向heating_region；不是把box顶面扩成无限平面。
2. **完整碰撞几何与姿态。** 从已forward的真实model/data恢复杯子全部39个box的root-local角点；确定性直立local+Z、world竖直yaw为基底yaw及+90/−90/180度。每姿态重算全部角点、底高、volume、有限支撑和墙/开门余量，包含门把手capsule。可行位置按姿态轮转，占用同一24预算；固定静态fixture产出4姿态各6条。AABB排斥包含原geom margins并保守拒绝重叠，可能漏掉可行种子，但不取代物理审计。
3. **完整A分量保护。** 只准种子改A7 qpos；builder独立从编译joint推导A7+6 whitelist，在第一次candidate restore前核对每个种子。整个base qvel、B门、机器人、其他物体及时间不变。实际HOLD收敛后移植测得的xyz/quat/qvel，不恢复旧quat、不清零速度、不锁物体。
4. **最小顺序入口。** `repair033_microwave prepare`直接绑定实际R3报告/sources的固定SHA，文件检查并复用全部20 ready及证书。新输出保留原字节副本，组合sources仍有90 expected。复用已有 `selected_preparation` 操作账本，只派发微波炉；0完成构造及paired replay、真正ready后才继续1..9。首0失败后9条保留not_attempted；派发但缺子证据保持interrupted/unknown，不能重试或补写通过。
5. **续跑。** `--continue`绑定相同输入/版本，不重跑failed/running/中断操作；首0仍不ready则不启动其余。0已ready时只继续后续未尝试的部分。完成构造而回放未尝试时复用原worker补回放。缺失旧20/已ready证据只阻断，不转为重建任务。

静态资产为LIBERO `8f1084e3132a39270c3a13ebe37270a43ece2a01`：microwave XML SHA256 `d06c1e44acb830c529a843e566deedfc5693a6e11f68a3d1d59d49021890fbdf`，mug XML SHA256 `134bfdb2e605b60609b63c4bae60d833ad027902973dfb6b912768e0870b435e`。中心底盒最低z=.00024，但轻微倾斜边缘盒使全部角点最低z约−.00009729327384；实现使用后者的逐姿态计算。直立完整extent约 `[.13972697,.10606173,.10321334]`，yaw90交换水平尺寸。测试包含全部39盒、真实6壳盒、门盒与3把手capsule，非理想圆柱近似；任务BDDL固定微波炉yaw=(0,0)。

## 判据及兼容性

没有修改资产、contact参数、摩擦、阻尼、solver、官方谓词、评分、v6 reader或策略图像。保留24候选、base80、每候选min80/max400、连续20、qvel0.01、原位置/穿透/机器人检查、150构造和2×150独立回放。未以延长等待作为修复。

冻结reader测试使用本轮真实文件producer/validator/writer与fake物理生成完整v6新method工件，再 `git archive 06817e61e07975279b4f3c4b29f410edc2357172 benchmark` 到隔离临时目录，用 `python -I` 导入固定旧reader。结果为新工件ready、archive/validate_snapshot通过；删除第二次独立回放audit后被拒绝。没有方法名放行例外，也没有改冻结目录。兼容性结论限于软件工件契约，不证明真实接触/稳定性。

## 实际执行的必要CPU/fake验证

Python 3.12.7；工作目录为独立R2分支工作树。RED阶段分别观察到新几何空实现5失败、builder未接method7失败、入口缺失/guard未接5失败，随后实现。没有重跑53/234/280全组，也没有全库或多平台测试。

```powershell
& 'C:/ProgramData/anaconda3/python.exe' -m pytest tests/test_task033_r5_geometry.py tests/test_task033_r5_builder.py tests/test_task033_r5_queue.py -q --tb=short --basetemp=.work/r5-final-targeted
# 33 passed in 4.84s

& 'C:/ProgramData/anaconda3/python.exe' -m pytest -q tests/test_task033_r2_settle.py tests/test_task033_r3_live_profile.py::test_selected_builder_passes_profile_and_records_manifest_identity --basetemp=.work/r5-builder-regression
# 11 passed in 0.58s

& 'C:/ProgramData/anaconda3/python.exe' -m pytest tests/test_task033_r2_integration.py::test_method_selector_is_bound_and_does_not_enable_normal00 -q --tb=short --basetemp=.work/r5-method-regression
# 1 passed in 0.07s

& 'C:/ProgramData/anaconda3/python.exe' -m benchmark.remaining_goals.headless.repair033_microwave --help
& 'C:/ProgramData/anaconda3/python.exe' -m benchmark.remaining_goals.headless.repair033_microwave prepare --help
git diff --check
# CLI help与diff check均exit0
```

覆盖几何逐姿态重算/有限支撑/旋转坐标、A完整whitelist与B保护、真实测得quat和非零qvel保存、24×400硬上限失败无导出、150+300、冻结reader证据完整性、首0构造/回放失败停9、首dispatch未知不重试、后续中断只续未尝试项、旧20/证书原样复用、缺失旧证据阻断。fake测试中的9,680计数是Python double调用，不是新增native样本。

独立审阅核对代码、XML、状态机和冻结reader测试，未发现阻断；额外独立queue8项通过（1.40s，与上述33重叠，不另计新增验证数）。

## 交付命令与下一步

完整、可复制的隔离部署、原venv配置、首0门控准备、续跑和进度读取命令见 [R5运行手册](../../docs/task033_r5_microwave_runbook.md)。服务器原输入固定为 `/HUBU-AI096/zp/ICML/task033_r3_06817e61/preparation/{sources.json,preparation_report.json}`，新输出为 `/HUBU-AI096/zp/ICML/task033_r5_fc2dd617/microwave_repair`。入口自动核对工单hash；不用手造来源或重做30条plan。

Codex审查并隔离部署，用户启动必要真实步骤。若首0仍不ready，交回失败/接触/控制账本后裁决，不再盲跑剩9。本轮未提出放宽速度阈值。已通过20、00九任务90和旧六60条10模型记录全部复用；等微波炉通过、30来源齐备后一次评新增30。没有部分20评测、allow-missing、自动eval或自动merge；旧结果不清理，033整体仍open。
