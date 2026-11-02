# 034｜二元合规成功率报告，不重跑或修改物理判据

2026-11-02。状态open，用户明确决定。X实现；Codex审查/部署与旧结果纯文件汇总；不启动真实实验。030方法训练代码并行开发，不等待本小任务。

## 用户决定

正式主结果只保留成功/不成功。成功=现有core全部合规成功条件通过；未全部通过=不成功。原UNKNOWN是证据诊断，不再是第三类论文/逐episode主结果。该规则统一用于baseline与所有改进模型，不按模型或某条视频例外。

当前九任务mask10正式90条：成功22=24.44%，不成功68=75.56%，技术错误/缺失0。旧67 failure＋1 unknown中，后者是`two_pots_s003_10`释放未确认；二元记0。成功分子、完整分母、轨迹、终止、视频、原生目标达成、释放证据均不变。

## 最小实现

- 固定已验收headless core行为不动；增加版本化纯报告映射`binary-compliant-success-v1`（字段/API等价可接受）。对既有**已验证、执行completed**的score row：`classification == success`记`success=true/outcome=success`，其余failure/unknown记`success=false/outcome=unsuccessful`。
- 输入仍走既有已验证结果/来源绑定读取；不得把任意损坏JSON或summary里的手填success当真值。现有正常加载链/纯文件证据复用，不追加物理回放或重渲染。
- 原row诊断与unknown reasons保留在diagnostics，不能将未知release改为false、伪造抓握/碰撞事实，不能全局字符串替换旧schema。新结果不覆写旧raw/summary。
- 控制台、正式Markdown主表和新summary逐episode明确二元结果与SR百分比/分母；unknown只在diagnostic证据字段出现，主表不再出现第三结果类别。任务总计与宏平均保持各任务等权，本九任务等样本时22/90。
- missing/technical/corrupt/interrupted不能假装模型不成功：保留运行完整性错误和完成进度；不静默剔除或缩分母。未齐时显示live completed SR＋完成率，不伪称正式完整分数。此为作业完整性，不是第三种已完成episode结果。
- 提供一个只读旧结果、输出新目录的普通python CLI；同一映射导出可由方法030的评测报告复用，不在方法库再写评分器。旧tri-state schema和历史旧报告兼容读取，不要求重建初态或改旧物理协议版本。

参考当前实现：`benchmark/remaining_goals/headless/metrics.py`及task033九任务汇总入口，固定已验收实现d8541ef4（main未自动合入PR14）。从main建立分支并明确依赖/复用PR代码，不自动merge旧PR、不假定main已有实现，不追带无关改动。

## 精简验收与交付

CPU/fake覆盖success→1、failure→0、unknown→0、technical/missing不伪装完成、重复/缺失episode被如实报告、映射前后原对象不变、逐task/总计与22/90合成用例一致。只防错分母/事实改写，不跑GPU/仿真或全库。

独立PR＋`collaboration/responses/034_round1.md`给出commit、受影响测试、实际CLI和公共报告API。Codex验收后对已有文件派生汇总，不做sim rescore，不改任一动作/目标/释放阈值/endpoint/旧数据。用户无须重新启动基线，也不因此新增训练前检查。
