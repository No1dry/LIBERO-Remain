# Codex：008 Round 5——历史XML资源兼容软件验收

2026-10-15。裁决：**accepted（R4明确P1修复），无进一步返修；008/Stage04未closed**。

[PR #5](https://github.com/No1dry/LIBERO-Remain/pull/5)已测试实现 `201457a46dfbb8c84ba41416eec08ffb1b64163b`，最终冻结 `089e0b7fa3916e6444b0880ca61101cac791c1ba`，tree `7aff772638ba75542e3fde4e5712a0c1ac8b9533`。实现到交付只有STATUS/response008_round3。238源码逐Git blob/SHA-256核验，未动原脏checkout。

## 本轮核对

- 精确历史chiliocosm根＋官方libero/robosuite资产段，按完整suffix重定位，允许根内..，规范化/resolve后严格contained；未知/歧义/缺失/越界/symlink逃逸明确失败，不按basename搜索。
- Expat定位原UTF-8的批准file值范围，只替换路径值，不重新序列化XML；材质、mesh缩放、物体/pose/camera及非路径字节不改。DTD/include/未知外部依赖拒绝。
- 扫描全部50 XML（含unused），在创建provider之前聚合全部错误；与运行时同一resolver。实际原XML/hash、根/映射/目标SHA/覆盖记录在scan，文件检查不能ready。
- provider开始和XML加载核冻结扫描；审计结束、audit/cache加载重核实际HDF/XML和目标资源SHA，scan由audit hash继承到cache/head，metadata不进policy。
- 唯一生产变化为finish/xml_assets.py、environment.py、data.py、cli.py。Codex AST确认_robot_contract/PandaPoseHold/_release/BasketContract/FinishLiberoEnv不变；provider恢复、truth、hold、close等R2关键方法不变。原两域/1313采样帧/GT/label/网络/阈值/指标不改，不加物理step。
- 保留旧v1历史读取，不将缺扫描的旧v2数据混成新可用数据。无当前已训练v2头需迁移，历史失败不改写。

## 独立软件证据

| 范围 | 实际结果 |
|---|---|
| 本地全套 | 1688 passed / 12既有可选skip，52.75秒，共1700 |
| 并行独立resolver/provider审查 | 97 passed / 0 skipped，0.82秒 |
| 并行独立data/CLI审查 | 92 passed / 0 skipped，8.80秒 |
| 服务器19个FINISH文件 | 457 passed / 0 skipped，58.95秒 |

12 skip为11个可选固定模拟器源码catalog检查和1个缺imageio_ffmpeg，与X Windows的15既有skip差异可解释，无新增008 skip。本地全套JUnit SHA `7166c4ba6dd9a5ad439f4f694b96ad167f15d33ec2326d46691da339fab1bf10`。

## 实际服务器文件检查与边界

新冻结目录已部署，完成真实HDF的register-data与同一resolver的全部50 XML扫描：4450/4450引用解析、87唯一原路径、errors=[]，file-only/非ready；详见[长期部署证据](../../docs/stage_summaries/stage04_task008_xml_fix_acceptance_2026-10-15.md)。不使用tiny测试冒称真实资源通过，不替换纹理/mesh，不创建作者home兼容软链。

软件与文件验收不证明后续物理layout/restore/release/K4/类别充分，不承诺真实audit必过；没有运行真实sim/状态恢复/物理label/VLA/feature/train/parity/eval。资产是当前固定runtime文件，未证明与不可访问的作者原文件字节相同；跨HDF/init物理祖源unproven仍保留。

解除本P1的PR合并暂停。X可保留最新README/Plan4/STATUS、R1..R5及旧失败和已审实现，合并PR并登记merge SHA；Codex不代合并，也不等待合并才运行冻结版本。禁止覆盖b596/9ddd旧失败。

下一步：用户按[新实际会话](../../docs/experiment_plans/stage04_task008_xml_server_runbook_2026-10-15.md)重跑同一1313帧audit；Codex读实际0/1/unknown、覆盖和身份，充分后直接给feature/训练命令。不新增独立预检、下载或VLA采集。交流/原始证据全保留，精确待删=[]。
