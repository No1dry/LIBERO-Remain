# 033 R8验收确认

身份：X。日期：2026-11-02。本轮已fetch main `f5bed1cbd93766051cf0dfa3b3575682ca98eaf0`，阅读 [033 R8审查](../reviews/033_round8.md)、最新STATUS、[部署阶段记录](../../docs/stage_summaries/2026-11-02_task033_r7_review_and_file_deployment.md) 和 [实际服务器命令](../../docs/experiment_plans/2026-11-02_task033_r7_server_commands.md)。本回复只记录验收，不提出或实施返修。

**已记录裁决：accepted，限R7软件、既有证据文件检查及隔离部署；无阻断返修，X本轮无修复待办。** [PR #14](https://github.com/No1dry/LIBERO-Remain/pull/14) 的已验收固定HEAD为 `d8541ef4a4bb4cc2e34c95b10227ea5fcaddaff9`，实现为 `c8c50e639b01802382b2bdfee73f0f946e8c465a`。本轮后续文档提交不替换冻结部署版本。

按R8记录，Codex独立定向CPU/fake为95 passed、0 skip、10.01秒；与X此前95项新增测试重叠，不能相加。此前153项受影响旧回归证据复用。本轮X没有重跑测试、服务器文件检查或任何真实命令。

已记录R8的服务器文件验收：源码归档及五个实现文件SHA一致；原R3两个输入、R5真实失败报告和固定XML核验通过；旧20来源/证书及20ready、1failed、9not_attempted身份保持。纯文件检查23.56秒，无仿真、restore/step、模型或训练。上述结果来自R8审查，不冒充X本轮独立服务器执行。

冻结代码为 `/HUBU-AI096/zp/ICML/LIBERO-Remain-task033-r7-d8541ef4`，输出根为 `/HUBU-AI096/zp/ICML/task033_r7_d8541ef4`。本轮不修改该目录或旧aedfe169/06817e61/942db12f源码、数据。实际部署后的运行路径以已发布的服务器命令为准，不重新部署到R7交付手册的建议目录。

新物理profile与RGB v6保持分离；新工件由新reader读取，旧20各自原profile复用。原规则、失败和raw保留，不追认旧settle采样为151点正式认证。软件accepted不等于物理通过：当前来源仍 **20/30 ready（66.67%）**，旧R5首源failed、其余9在该次未尝试；R7真实效果待用户运行。新三30条模型尚未启动，正式10模型记录覆盖60/90，00仍78/90成功且覆盖完整。

后续由用户启动必要真实构造与两个独立回放；固定0真ready才派发1..9，失败即停。Codex读回实际报告，齐30后再给一次新增30条10模型命令，不部分20、不allow-missing、不重跑旧六/00/旧20、不自动串联评测。

本轮只同步协作文档，已核对源码/测试/配置与冻结HEAD一致；不改冻结部署、不启动实验/训练、不自动合并PR、不清理历史。033整体仍open，待删=[]。
