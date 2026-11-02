# Task033 R3软件验收、旧证据复验及隔离部署

日期：2026-11-02。此阶段完成软件和纯文件准备，不是完成物理补建或模型评测。

## 裁决

**accepted，限本轮软件、原记录复验和隔离部署；无阻断返修要求。** 033整体仍open，真实补建22来源与新增30条10模型尚未运行。没有自动merge、训练、重跑00或历史清理。

- 统一 `named-uint8-rgb-one-level-v6`从构造、formal reset/回放到audit/manifest/profile/reader贯通。实际uint8最大通道差≤1；面积只记录；0↔255不溢出。非RGB初态精确、动态1e-8，以及状态/相机/hash和既定物理/语义门槛保持。
- 旧v4缺省解释、旧五ready和旧失败不变。派生证书只重新解释完整原记录，绑定全部依赖，记录 `recorded_diagnostics_revalidated=true`、`raw_rgb_recomputed=false`、`new_native_steps=0`，不假称新鲜像素或新的独立物理测量。
- 缺第二窗口不能派生完成，构造证书只能配明确v6新回放；证书/依赖漂移在native前被拒绝。续跑不自动重试失败/运行中/中断的来源。抽屉和微波炉已验收R2算法未返工；评分、模型和策略图像未改。

## 独立软件证据

Codex仅运行本轮五个R3测试文件，**53 passed，0 skip，8.56秒**，未重跑R2的280全组。覆盖数值规则、live接线、旧证据、队列、完整reader及归档边界。X的234项组合是其交付事实，不与本次53重复相加。源码归档SHA-256：`f517dc13ba78a13d936b1d3fcf406feb1bd38897ca807a1a0bce1bb3672a5306`。

## 服务器纯文件结果（不是新增仿真）

代码：`/HUBU-AI096/zp/ICML/LIBERO-Remain-task033-r3-06817e61`。
新输出根：`/HUBU-AI096/zp/ICML/task033_r3_06817e61`。冻结aedfe169目录和原证据均未修改。

`repair033_v6 plan`在实际服务器工件上exit0，18.09秒；`reuse_issues=[]`、blocked=0，plan文件SHA为 `fde5ce4b388c5959d278695d58cc0b2a2f099eda9040a57572a599ae40d991e8`：

| 分路 | 来源数 | 当前含义 |
|---|---:|---|
| reuse_only | 5 | two_pots 1/3/4/5/6旧ready原样复用 |
| derived_ready | 3 | two_pots 0/2/8完整原构造与两回放逐帧复验通过；独立v6证书，无新native |
| repair | 20 | 抽屉10、微波炉10，待用户按已验收R2方法补建 |
| replay | 1 | two_pots 7，保留构造；既有成对入口300步，待用户执行 |
| build | 1 | two_pots 9原manifest无选中episode，待用户最小构造及回放 |

新增三任务10来源现有8/30=**26.67%**可用，仍22个需用户真实步骤，不声称30ready。包括旧六的正式10模型记录覆盖仍60/90=**66.67%**；没有新增模型成功率。九任务00仍78/90=86.67%，覆盖100%，不重跑。

## 交接

用户可直接按[部署后完整命令](../../docs/experiment_plans/2026-11-02_task033_r3_server_commands.md)启动必要来源补建。Codex读取真实报告后给新增30条10模型命令；不要在本阶段自动串联eval，也不要运行旧v4二十条命令。X本轮无修复待办，保留PR及回复，不自动合并或修改冻结部署。待删清单=[]。


## 证据与归档

- GitHub交付：PR #14，X回复 `collaboration/responses/033_round3.md`，固定源码06817e61；R2物理软件结论直接复用，未另要求返工。
- Codex本地：`reports/task033_r3_review_2026-11-02/`保存源码归档、53项CPU/fake JUnit、文件部署脚本、原始plan/派生证书/部署receipt及完整命令。
- 新v6接受0/2/8基于原始逐帧诊断和两个原回放，原raw/hash/失败保留；明确不重算未保存fresh RGB，不声称模型对一码值差不变。
- 不启动真实作业，不加载模型，不推送实现代码，不自动merge，不清理交流；精确待删=[]。
- 本总结及review/命令同步GitHub与本地 `research_archive/LIBERO-Remain/`，来源commit和SHA记录于backup_manifest.json。

本阶段交流：033 R3工单、033 R3回复、033 R4审查仍随033开放任务保留。后续真实22来源及新增30条10结果未交回，不能标033整体closed；030数据增强训练仍未启动。
