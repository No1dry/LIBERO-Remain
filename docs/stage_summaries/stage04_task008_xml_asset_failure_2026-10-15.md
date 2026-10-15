# Stage04：9ddd真实audit被历史XML资源路径阻塞

2026-10-15。用户第二次运行同一1313帧audit，冻结9ddd40f2968ed5dc3d0e0be59db00b8e91d28e5c。status=insufficient、command_exit=2/tee_exit=0；provider_identity存在，restore_attempts=1但rows0/hold0，尚无标签或模型成绩。旧初始化P1已越过；本次错误是首帧旧作者路径`/home/yifengz/workspace/libero-dev/chiliocosm/assets/scenes/../textures/seamless_wood_planks_floor.png`无法被固定LIBERO helper重定位。

根因与[008 R4最小修复要求](../../collaboration/reviews/008_round4.md)已提交X：官方helper只识别独立libero/robosuite段，不识别chiliocosm旧根。需要明确批准根→固定LIBERO/assets的完整suffix映射、规范化后contained、每资产SHA与全量依赖检查；不建系统软链、不替换素材、不改源HDF/XML、几何/相机或物理标签。

## 全量只读文件排查

Codex读取实际50个HDF model_file，未创建环境/恢复/渲染/加载模型。4450次file引用（mesh3700、texture750），去重87原路径；63个robosuite可按官方规则映射、24个chiliocosm旧根需补规则。87/87（100%）对应固定本地文件候选存在且contained，无缺候选。87个原路径均出现在全部50轨迹中。当前无include，compiler有meshdir=meshes/但全部实际file路径绝对；扫描未应用映射、未认证物理布局或label。

[完整实际库存](evidence/stage04_task008_xml_assets_2026-10-15.json)记录原XML hash、每条引用与本地候选/hash。映射候选不是与旧作者机器原资产逐字节对过的证明；后续须由X运行时同一resolver处理，Codex部署时用实际50XML再核，不能把此次临时诊断当正式解析通过。

## 原始证据及边界

- report：`/HUBU-AI096/zp/ICML/stage04_finish_9ddd40f/results/run01/audit/audit.json`，文件SHA `ad035bc1168bcade689e5a7f527d923abd5d44d32abfb0c81a8fbaf449d46fbd`，内部audit hash `7792a6db60a24deb82053d83b61a226003a2c8ef63cd6ba8658474659796c3cb`。
- log：`/HUBU-AI096/zp/ICML/stage04_finish_9ddd40f/logs/run01/03_audit.log`，SHA `dde9517edd48e62223f20853ac9f1c27cd27320a175096d2f0711c4462cc0ae5`。
- 本地项目reports/stage04_task008_xml_failure_2026-10-15/evidence/两份已核SHA；asset_inventory.json与inspect_xml_assets.py保存CPU诊断，不是benchmark实现。

R3的软件修复/414测试仍保留，不能推导真实audit可用。实际有效标签仍0、没有feature/head/parity/calibration/eval或新视频；无模型0%结论，也不把技术故障算数据类别不足。HDF/eval物理祖源unproven、成功示范负例覆盖限制不变。

本P1处理前暂停PR #5合并和同版audit重跑。X只修兼容→Codex审查/新部署与全量纯文件检查→用户仍只启动原audit；不新增独立预检、下载或采集。文件检查全通过也不承诺后续真实物理audit必过。各版本原始数据和用户脏工作区保留。

任务007/008及Stage04未closed；新开放review008_round4连同R1/R2/R3、responses均保留。精确待删清单=[]，无删除。总结/审查/资源库存/STATUS发布后按README本地来源commit与SHA核验归档。
