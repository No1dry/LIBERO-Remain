# Stage04：OFT 8维输入证据修复验收与feature-only重试部署

2026-10-16。本记录是工程子阶段验收，**不是Stage04科研完成**。研究目标仍为外部提前完成部分目标后，VLA能否重定剩余目标、保留已有成果并合规完成／停止；FINISH只控制未学停止的混淆，不人为压低基线。

## 本次完成

X按[R8](../../collaboration/reviews/008_round8.md)最小修复：proprio证据合同由误写7维纠正为原模型实际8维；动作仍7维、chunk8、56-token特征不改。生产diff仅finish/schema.py，错误含expected/actual形状与dtype；capture、worker、BF16 bit保真、原始预处理、动作、冻结／RNG、labels/splits/指标均未改。tested ec5e119582245e0dde957d3e251020f8ebbb030e，final3433f487d38efe0a08e4c814e87412aad5aba9fe相对tested仅回复与STATUS。

Codex[R9软件accepted](../../collaboration/reviews/008_round9.md)，无新增返修。独立本地1833 passed／12环境skip；服务器FINISH专项602 passed／0skip；另独立124及7项CPU/fake复核通过。真实224×224／12C BF16／8D经原capture、wire、typed NPZ和cache消费者逐bit一致；synthetic tiny train／32parity只是软件测试，不冒充真实研究训练。

新固定源码/HUBU-AI096/zp/ICML/LIBERO-Remain-stage04-finish-3433f48，新运行根/HUBU-AI096/zp/ICML/stage04_finish_3433f48。262源码逐Git blob及SHA256、11冻结部署文件已在本地和服务器核对；runtime SHA75f2a711a39c58a07715b3a280aeba26a29dfbba70caf87cc051520f0a3f9720不变。仅新增目录，未升级环境、换checkpoint、合并PR或改现有脏工作区。

## 原audit直接复用

新源码只读validate_audit与1313观测逐文件核验通过，内部SHA44d0ab96f910221b58f2bfc930c6e1a06db79f23f19755318cd6d34764bf8457、文件SHA294120c4c0a557a6211db1ed44c9d3a1a8915edcae1ad2e2a0611d98fb501dce不变。不重新仿真恢复、hold或生成标签。session的AUDIT绑定原2cb成功目录，features／04_features.log指向新3433运行根，旧失败partial／日志不覆盖。

| 角色 | label0 | label1 | unknown | 可导出 |
|---|---:|---:|---:|---:|
| head_train | 1048 | 23 | 44 | 1071 |
| head_validation | 188 | 2 | 8 | 190 |
| 合计 | 1236 | 25 | 52 | 1261 |

1313帧采样已完成100%，已知标签覆盖96.04%；这不是模型成功率。验证正例仅demo_38两帧，正例覆盖有限；跨域物理祖源独立性和SOG10 exposure未证明、演示缺失败／停滞负例、HDF额外碰撞geom域差异仍披露。不因pilot正例少临时换split、看测试调头或新增门槛。

## 还没完成与用户下一步

用户按[完整新命令](../experiment_plans/stage04_feature_retry_runbook_2026-10-16.md)亲自启动一次1261已知帧特征重导出；Codex没有启动真实VLA作业。完整cache身份、行数与hash核验后才交小头训练命令，随后真实parity、普通停止校准／独立测试，再做Remain。当前无真实finish头、parity／校准或新协议模型评分；不能宣称stop-capable或科研假设已验证。此前失败可能完成过forward，实际成功计数未知。

[机器可读证据](evidence/stage04_input_contract_fix_2026-10-16.json)。本地报告reports/stage04_task008_input_fix_2026-10-16／相邻CPU JUnit；服务器verification下CPU JUnit／log／audit复用回执均备份并核对SHA。原1313份观测仍留服务器，不声称全量本地复制。

交流tasks/008、responses/008_round1–5、reviews/008_round1–9均保留；007未科研closed，008 accepted软件不等于closed。X可按R9保留最新main文档合并已审实现，Codex不代合并，本次运行pin不变。精确待删=[]，未删除任何原始数据或交流。本总结／证据／命令／裁决按README提交GitHub并本地备份来源commit及SHA。
