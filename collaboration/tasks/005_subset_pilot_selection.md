# 给 X：005 只选10/01/11的有界pilot及隔离可执行性诊断

作者：Codex。日期：2026-10-09。状态：open。阶段：Stage03 / Plan3。
前提：003代码已accepted，PR #2仍待合并登记；004版本记录问题另有任务。先按既有授权合并003并记录main，再从明确基准开独立实现分支；不要把005未审代码混入旧实验。
完整计划：[Plan3](../../docs/experiment_plans/stage03_subset_pilot.md)。X只实现/测试/推送，不启动GPU；模型与状态实验由Codex执行。
用户澄清修订：主动观察/合理试抓及空抓反馈利用属于被测能力；006的初始可观察性闸门撤销且改非阻塞诊断。优先交付本任务，不为让答案显眼而修改当前001状态/camera/crop；基本技术/语义有效性仍核对。主15条先测原模型，最多10条执行oracle另列作后续解释，不以oracle失败筛主样本。

## 为什么需要此最小变更

用户已明确中心问题是外部提前完成任意子集后的剩余目标重判。00正常能力5+5成功已完成，主结果只要10/01/11的JSR↑/UIR↓。
当前 `evaluation.run()` / `cli.evaluate()` 迭代完整manifest的所有episode。完整配对校验要求00/10/01/11齐全，直接删00、拆旧manifest或放松完整性检查都不是正确实现。

## A. 显式选择、计划与分母

1. 增加显式mask选择，默认all保持旧行为。用户指定10/01/11时，在完整源bank/replay通过原有检查后只调用这些episode，固定basket来源0..4→expected15。mask解析严格检查类型/宽度/重复/未知项；不得按文件序号推断语义mask。
2. 保留源manifest/state包/replay原字节。保存完整源manifest/hash和准确执行选择/expected IDs/hash；运行身份、配置hash和后续read_run/rescore/report均核对选择。可采用清楚的selection metadata或独立purpose/schema，不能把不完整子manifest假冒旧完整benchmark。
3. 未选00明确not_selected，不调用模型，不记为error/missing/策略失败。所选准备错误、运行错误、未尝试/missing保留在其expected分母；不会补index或过滤policy失败。
4. 提供不加载模型/不创建仿真的dry-plan，输出源/replay身份、task/index/mask/IDs、原指令、有效指令、预算、模型配置及准确expected数量。来源0..4不是“前5个模型会成功的来源”。
5. 10/01沿用H520/W150，策略670步；11沿用W150，不真值early-stop、不改变动作/归一化/RNG。每episode重置seed7与队列沿用已有协议；模型load/reset次数如实声明。

## A2. 必须落实的技术暂停、实际step0和决策时点证据

Codex核对X的独立回应后纳入本任务硬验收，不留作执行者“盯日志”的约定：

1. 显式pilot技术故障暂停。模型加载/初始化/运行接口错误、初态不匹配/恢复错误、录像错误或缺失、实际step0保存/验证失败等发生后，落盘已有/部分证据、停止后续所选case、登记准确停止原因并关闭资源。原expected15（诊断10）不缩小；未尝试项保留missing，出错与policy任务失败分开。完整技术执行但success=False继续，不筛样本。旧默认all继续行为保持兼容，pilot暂停策略预先声明并纳入运行身份；不能只靠exit0判断。
2. 保存本次实际env.reset返回、runner白名单整理后用于首次predict的step0 typed NPZ，绑定实际episode/选择/模式和观测hash。不能以构造阶段NPZ冒充；不为存证额外reset/render/step，不修改返回观测或模型输入，不放入目标真值。源构造观测和此次实际起点分别标记；错误时仍保留可用起点/partial证据。
3. 记录真实policy query的决策观测步、query序号、实际动作块长度/执行区间或等效可核验映射，首次query对齐观测0，后续按真实队列耗尽位置，不假设所有模型固定8步。错误/STOP/最后截断chunk正确保留。不为记录增加predict/render/step或改变chunk/RNG。可保存观测hash辅助绑定，不要求保存所有最终encoder tensors/全部query NPZ。
4. 模型真实输入按既有OFT预处理/crop与实际proprio/指令解释；录像仅辅助，不冒称未裁剪全幅就是模型所见。新反馈出现在chunk中间时，下一query之前的预排动作不能直接被称为“拒绝利用反馈”。事件时点是诊断证据，不增加主metric。

## B. 明确隔离的oracle-remaining-initial诊断

用途仅是同一状态的剩余执行可行性正证据，不是主模型分数或新方法成绩。

- 显式选择诊断模式；只对10/01运行，5×2=expected10；不对11虚构剩余指令。原模式默认原完整指令，禁止从mask/predicate为原模式增删指令。
- 源episode的官方instruction和完整goal specs保持不变，仍用于恢复/身份/评分。只在显式诊断的policy调用边界传固定effective_instruction，并绑定两者；不能通过改源episode instruction绕过环境或read_run/标注身份。
- 诊断仅按初始mask选未完成goal的catalog language；本批单剩余目标。完整原始指令、有效指令、mask来源、诊断purpose/mode/hash显式保存，不能改源manifest以掩盖真值使用。
- 与原模式使用完全相同state、恢复、goal specs/预算/保持/评分与checkpoint，仅诊断的有效指令不同。任务完整goal/preservation评估不删已完成goal；适配器不接收额外真值传感器。
- 与主结果分独立输出/用途；诊断JSR不混入主JSR/UIR，派生报告显著标明oracle-conditioned diagnostic。joint成功提供正证据；失败仅未证实，不声称物理不可达。
- 不实现通用router、prompt scaffolding、学习probe、STOP token或新训练。若接口不适合复用，可提供最小独立entry，明确purpose及身份，旧默认路径兼容。

## C. 主表与UIR兼容性

- 主表10/01/11各一行，JSR/UIR两列；00能力控制另存旧报告，不添加第三个主分数或将00/11并入partial macro。
- UIR template/report的身份和expected分母必须绑定实际执行选择；未标注=N/A，unknown/覆盖率完整，不把未选00列为UIR缺失。
- 信息获取必要性纳入人工rubric：看桌面、找篮子、移动腕部视角、合理无破坏试抓及空抓反馈不自动记UIR。不得实现“初图目标不可见即invalid”或“尝试次数超阈值自动UIR”等过滤/计分；合理探查和持续无效重做由完整证据判断，疑义unknown。
- UIR事件必须绑定当时已满足的目标（或整体完成）、操作对象/目标及缺乏任务/合理信息获取必要性的证据。对尚未完成目标反复抓取失败属于执行失败，不因重复/无进展直接记UIR；评估器真值不能替代策略当时的实际信息和query机会。无法确认对象、状态、必要性或审核覆盖保留unknown。
- 旧10项原分数/trace保留，主指标语义不变。reason/evidence可以记“外部已完成目标重做/整体完成后多余操作/必要检查或收尾”，不得自动从动作、闭爪、predicate、接触或没STOP赋UIR布尔值。
- 不改写历史raw、旧summary、旧UIR标签；只读派生到新目录。旧默认all与既有测试/模板/报告不回归。

## CPU/fake验收要求

至少覆盖：源仍完整校验；15和10准确IDs/分母；00未选不调用；mask宽度/重复/未知拒绝；selector/源/replay/hash篡改拒绝；实际所选error/missing保留；primary原指令严格不变且无真值泄漏；诊断指令准确且单独标注；11没有虚构oracle输入；670/150与seed/queue不变；derived-report/uir-template/read_run/rescore兼容；源/旧报告全字节不变；新输出不覆盖。
补充必测：runtime/invalid-reset/video/actual-step0错误会暂停且后续不调用、expected不缩小/missing准确；success=False完整case仍继续；实际reset观测区别构造参考且typed NPZ/hash正确；捕获没有额外reset/render/step/predict和输入变异/真值泄漏；query步及chunk截断/STOP/异常对齐；oracle只在policy调用边界改有效指令；默认all旧行为/旧raw字节兼容。UIR仍人工，不新增未完成目标失败自动标签。
如果同时提交004修复，单独commit与测试说明，由Codex分别验收。不要扩成未请求的model/evaluator重构。

## 交付

独立PR，`collaboration/responses/005_round1.md`：明确base/实现SHA、变更文件、actual测试结果、两种模式dry-plan（15/10）及CLI可复制命令、兼容性/未完成项。不能只写“可以推进”。
等Codex独立代码/CPU审查后冻结新实验提交，再由Codex执行；不自行合并005、不跑GPU、不关闭科学阶段。
