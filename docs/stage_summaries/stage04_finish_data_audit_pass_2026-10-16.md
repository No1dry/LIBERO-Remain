# Stage04：真实示范数据审计通过，进入冻结OFT特征阶段

2026-10-16。用户亲自启动冻结2cb1428f312175968ac42449994c219e94e9ab14的03_audit，已完成；Codex只读审查后接受本数据审计子阶段，**允许按原计划进入feature，Stage04整体/模型效果/008闭环未完成**。不重跑audit，不新增采样/分组/标签门槛。

## 真实审计结果（不是模型成功率）

status=ready_for_feature_export，issues=[]，command_exit=0/tee_exit=0。预定1313/1313采样帧完成（100%），train30轨迹/1115帧、head_validation5轨迹/198帧；unused15轨迹及eval init没有用于恢复或标签补样。

以下比例以各组全部采样帧为分母：

| 组 | label0：不可FINISH | label1：可FINISH | unknown |
|---|---|---|---|
| head_train，1115帧 | 1048（93.99%） | 23（2.06%） | 44（3.95%） |
| head_validation，198帧 | 188（94.95%） | 2（1.01%） | 8（4.04%） |

已知标签1261/1313（96.04%）：训练1071=1048负+23正，验证190=188负+2正。unknown52（3.96%）均由现label合同记为release_evidence_missing，保留未知，不当负例或补造正例；特征/拟合排除它们。25个独立同状态K4保持分支，记录100个实际保持步；1313是采样恢复计数，不声称包含所有hold分支内部恢复调用。

最终兼容metadata有1次known_basket_link7_collision加载，无错误；真实HDF全部XML本身相同，当前审计保留原碰撞体/模型变体。没有修改eval/source001、标签、K4、网络、阈值或评分。兼容/状态恢复/标签审计在本次预定样本范围内通过，不外推未知模型或W150。

## 数据限制与推进裁决

训练正例23帧分布于11条轨迹：demo_5/8/9/12/15/16/20/21/23/28/34。验证正例仅2帧且都来自demo_38，占已知验证190帧的1.05%；不是两次独立停止episode，普通validation BCE对完成类选择会很脆弱。极不平衡及轨迹相关性应披露，不能靠高overall accuracy宣称模型会停止。

当前满足已冻结合同：全采样完成、无关键issues、两head组各有已知0与1、unknown显式保留。原合同没有“至少X个验证正例”的额外门槛，故不临时改split/标签、挑容易正例或追加采集。只用训练已知类计算pos_weight=1048/23≈45.5652；仍原seed7/MLP/AdamW、最大50epoch、普通validation BCE最小且最早tie；不借normal_calibration/test/Remain拟合或选checkpoint。

因此继续原定1261次feature forward，再由用户单独启动head训练。真正普通停止能力仍由原定normal_calibration5条shadow及独立normal active10条检验；audit ready/低BCE不等于stop-capable。当前未运行本阶段VLA forward/feature/head/parity/calibration/eval，没有新模型成绩或视频，默认30条模型rollout预算未消耗。

## 身份、复核与备份

源码/配置仍原2cb不可变部署。内部audit SHA44d0ab96f910221b58f2bfc930c6e1a06db79f23f19755318cd6d34764bf8457；audit.json文件SHA294120c4c0a557a6211db1ed44c9d3a1a8915edcae1ad2e2a0611d98fb501dce；03_audit.log SHA f9b8c049894f4376823c88ea932fcc8f9b4313fd5fa1ee6487714f5b2949b6cf。

Codex在服务器以该版validate_audit(base_dir=实际audit)完整复算来源/实际文件SHA/XML资产/物理label证据/全帧覆盖及1313个观测NPZ身份，通过；没有创建环境或调用模型。报告与日志已下载项目reports/stage04_task008_audit_pass_2026-10-16/evidence/，逐SHA与服务器一致；原1313份观测仍保留服务器并已完整hash复核，未声称全部复制到本地。[精简验收回执](evidence/stage04_finish_data_audit_2026-10-16.json)记录计数/来源和边界。

下一输出features与04_features.log均不存在，避免覆盖；原冻结checkpoint目录存在，文件系统空间检查无当前阻塞。Codex不代启动下一阶段。

## 下一步：用户启动一次feature导出

登录服务器后：

~~~bash
bash
source /HUBU-AI096/zp/ICML/stage04_finish_2cb1428/session.sh
finish_sim 04_features export-features --audit "$OUT/audit" --runtime-config "$CFG/oft_sog10.json" --out "$OUT/features"
~~~

该命令会加载原OFT并进行1261次冻结同forward特征提取，不训练动作网络，也不自动训练finish head。输出results/run01/features/feature_export.json与cache，日志logs/run01/04_features.log。完成后Codex核cache/输入/行数/来源/base/特征身份，再给单独训练命令。真实阶段仍由用户启动。

本轮没有代码实现修改或返修，不自动合并PR。008/Stage04未closed；旧失败/诊断/新成功raw均保留，精确待删=[]。总结/回执/STATUS/手册更新提交GitHub并按README本地来源commit及SHA归档，不删除交流。
