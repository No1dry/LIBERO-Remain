# 给 X：005 只选10/01/11的有界pilot及隔离可执行性诊断

作者：Codex。日期：2026-10-09。状态：open。阶段：Stage03 / Plan3。
前提：003代码已accepted，PR #2仍待合并登记；004版本记录问题另有任务。先按既有授权合并003并记录main，再从明确基准开独立实现分支；不要把005未审代码混入旧实验。
完整计划：[Plan3](../../docs/experiment_plans/stage03_subset_pilot.md)。X只实现/测试/推送，不启动GPU；模型与状态实验由Codex执行。

## 为什么需要此最小变更

用户已明确中心问题是外部提前完成任意子集后的剩余目标重判。00正常能力5+5成功已完成，主结果只要10/01/11的JSR↑/UIR↓。
当前 `evaluation.run()` / `cli.evaluate()` 迭代完整manifest的所有episode。完整配对校验要求00/10/01/11齐全，直接删00、拆旧manifest或放松完整性检查都不是正确实现。

## A. 显式选择、计划与分母

1. 增加显式mask选择，默认all保持旧行为。用户指定10/01/11时，在完整源bank/replay通过原有检查后只调用这些episode，固定basket来源0..4→expected15。mask解析严格检查类型/宽度/重复/未知项；不得按文件序号推断语义mask。
2. 保留源manifest/state包/replay原字节。保存完整源manifest/hash和准确执行选择/expected IDs/hash；运行身份、配置hash和后续read_run/rescore/report均核对选择。可采用清楚的selection metadata或独立purpose/schema，不能把不完整子manifest假冒旧完整benchmark。
3. 未选00明确not_selected，不调用模型，不记为error/missing/策略失败。所选准备错误、运行错误、未尝试/missing保留在其expected分母；不会补index或过滤policy失败。
4. 提供不加载模型/不创建仿真的dry-plan，输出源/replay身份、task/index/mask/IDs、原指令、有效指令、预算、模型配置及准确expected数量。来源0..4不是“前5个模型会成功的来源”。
5. 10/01沿用H520/W150，策略670步；11沿用W150，不真值early-stop、不改变动作/归一化/RNG。每episode重置seed7与队列沿用已有协议；模型load/reset次数如实声明。

## B. 明确隔离的oracle-remaining-initial诊断

用途仅是同一状态的剩余执行可行性正证据，不是主模型分数或新方法成绩。

- 显式选择诊断模式；只对10/01运行，5×2=expected10；不对11虚构剩余指令。原模式默认原完整指令，禁止从mask/predicate为原模式增删指令。
- 诊断仅按初始mask选未完成goal的catalog language；本批单剩余目标。完整原始指令、有效指令、mask来源、诊断purpose/mode/hash显式保存，不能改源manifest以掩盖真值使用。
- 与原模式使用完全相同state、恢复、goal specs/预算/保持/评分与checkpoint，仅诊断的有效指令不同。任务完整goal/preservation评估不删已完成goal；适配器不接收额外真值传感器。
- 与主结果分独立输出/用途；诊断JSR不混入主JSR/UIR，派生报告显著标明oracle-conditioned diagnostic。joint成功提供正证据；失败仅未证实，不声称物理不可达。
- 不实现通用router、prompt scaffolding、学习probe、STOP token或新训练。若接口不适合复用，可提供最小独立entry，明确purpose及身份，旧默认路径兼容。

## C. 主表与UIR兼容性

- 主表10/01/11各一行，JSR/UIR两列；00能力控制另存旧报告，不添加第三个主分数或将00/11并入partial macro。
- UIR template/report的身份和expected分母必须绑定实际执行选择；未标注=N/A，unknown/覆盖率完整，不把未选00列为UIR缺失。
- 旧10项原分数/trace保留，主指标语义不变。reason/evidence可以记“外部已完成目标重做/整体完成后多余操作/必要检查或收尾”，不得自动从动作、闭爪、predicate、接触或没STOP赋UIR布尔值。
- 不改写历史raw、旧summary、旧UIR标签；只读派生到新目录。旧默认all与既有测试/模板/报告不回归。

## CPU/fake验收要求

至少覆盖：源仍完整校验；15和10准确IDs/分母；00未选不调用；mask宽度/重复/未知拒绝；selector/源/replay/hash篡改拒绝；实际所选error/missing保留；primary原指令严格不变且无真值泄漏；诊断指令准确且单独标注；11没有虚构oracle输入；670/150与seed/queue不变；derived-report/uir-template/read_run/rescore兼容；源/旧报告全字节不变；新输出不覆盖。
如果同时提交004修复，单独commit与测试说明，由Codex分别验收。不要扩成未请求的model/evaluator重构。

## 交付

独立PR，`collaboration/responses/005_round1.md`：明确base/实现SHA、变更文件、actual测试结果、两种模式dry-plan（15/10）及CLI可复制命令、兼容性/未完成项。不能只写“可以推进”。
等Codex独立代码/CPU审查后冻结新实验提交，再由Codex执行；不自行合并005、不跑GPU、不关闭科学阶段。
