# 034 R1｜二元合规报告软件验收与隔离部署

2026-11-03，Codex。PR15固定HEAD `cb8aca6aca0864bb9a304bdf2471b5025b371479`，实现 `d2afce4eb074b777364daddea2c08bd70731865f`。**accepted，限二元报告软件与隔离文件部署；不修改原物理评分、原raw或基线轨迹。** PR未自动merge。

## 证据与边界

- Codex独立12/12定向CPU/fake通过（100%，0skip，0.79秒），源包SHA256 `0ff8ceab0db9a5d1225213820a292d446bda3a9c86feb0702d019b6ac48e25a0`。
- 已审completed success→1，completed failure/unknown→0；缺失/运行错误/损坏/混模型不冒充模型0或完整SR。正式分母齐全且无完整性错误才有formal_SR；原证据留diagnostics，接口不改目标/释放/确认/动作/终点。
- 报告依赖固定d8541ef4既有reader，单独子进程激活，不复制第二评分器；验证source/result绑定，保持原证据级别，不冒称未读视频/原raw也已复验。
- 代码已上传独立新目录并核对归档SHA，无pip升级/旧core热改；方法030可以按固定报告包字节复用，不被本轮030数据缺口连坐。

## 原90条派生报告

Codex已启动本任务允许的**纯文件报告派生**：读取旧六原baseline＋已有table-support rescore，以及新三原30条10记录，另存新目录。没有模型加载、GPU、仿真、恢复、回放、渲染或任何episode重跑。此是结果分析，不是用户独占启动的真实实验。

在本裁决撰写时reader仍在处理原文件，尚未宣称实际90条派生报告完成；已验收基线22/90=24.44%、不成功68/90=75.56%保持，不能拿合成测试冒充本次实际产物。完成后单列文件输出及SHA；不因该文件读取给用户新增实验命令或阻塞030修复。

## 030关系及下一步

034本轮X无需返修。030 PR9训练/adapter/评测主体保留，但真实proprio字段误拒绝和实际进度监督生产路径需补齐，见方法库[030 R1](https://github.com/No1dry/Learning-Not-to-Act/blob/main/collaboration/reviews/030_v2_round1.md)与[集中修复工单](https://github.com/No1dry/Learning-Not-to-Act/blob/main/collaboration/tasks/030_v2_round2_production_data_path.md)。不是要求整套重写/全库测试。

034软件范围accepted，最终实际旧结果派生尚待读完；不重开033基线，资料/旧未知事实保留，未删除、合并或启动任何真实实验。下一步Codex收齐文件派生结果；X只修030两项，用户暂不启动新实验。
