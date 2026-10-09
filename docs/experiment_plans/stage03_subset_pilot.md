# Plan 3：外部部分完成后的剩余目标重判（首批 pilot）

日期：2026-10-09。研究决策/执行/审查：Codex；代码实现：X。
当前阶段：Stage03。主实验只评价10/01/11；00是已完成的能力对照。
用户已确认推进本阶段；旧plan2保留历史，因子矩阵、训练、probe/router等旧计划不继承为本阶段授权。

## 1. 研究问题与最小主表

当人或外部过程提前完成任意部分任务后，VLA能否根据当前观测重新确定剩余目标，并在保留已有成果的同时完成任务？

允许模型通过预算内的主动观察和合理试探获取信息、利用反馈后调整行动；不要求第0帧直接给出完整完成证据，不要求一开始零动作/立即跳过。

主表按mask分别列两项：JSR↑、UIR↓。00/official另列能力对照；不把00、partial、11混成一个总分，不增加步数/闭爪次数/STOP率等主指标。

- JSR：沿用已审代码。10/01要求H内完成剩余目标、初始已完成目标在全窗口保持、最终H..H+W稳定满足；11要求0..W初始全目标保持。
- UIR：完整录像审核是否对当时已满足的目标进行无必要任务操作，或整体完成后仍进行无必要任务操作。须绑定对象/目标状态与任务/信息必要性证据；对未完成目标反复抓取失败不直接计UIR。缺标注为N/A；unknown、有效分母及覆盖率必须显示，不按0处理。
- 必要性包含信息获取：查看桌面是否有物体、寻找篮子/移动腕部视角、合理无破坏试抓并利用空抓反馈、必要释放/安全撤离均不自动算UIR。不允许把完成目标撤销后完整重做再当作“合理试探”。只凭动作/闭爪/接触/没STOP不能自动生成UIR；chunk内多个闭爪步不等于多次尝试。
- 标注reason/evidence区分外部已完成目标重做、正常全部完成后的多余操作及必要收尾。后一类单独出现不能证明外部目标识别失败；这是证据类别，不是第三个主指标。
- 10失败是待验证假设，不是验收条件。原模型若正确跳过或继续，照实报告；不筛失败状态。

## 2. 固定身份和样本

任务：LIBERO-10 basket，同一原始完整指令，两目标按catalog排列：
goal0 = soup_in_basket（alphabet_soup_1）；goal1 = sauce_in_basket（tomato_sauce_1）。
10：soup已在basket，只剩sauce；01相反；11两个都完成。位编号不是示范的强制时间顺序。

同一SOG10 OFT checkpoint，来源snapshot638918f3d1c2e43a39a8a20772bdb8b91835e4b7。
本轮使用用户指定A100 80GB机器、/HUBU-AI096/zp/ICML；不记录凭据。
policy seed7，chunk8，center_crop=true，BF16既有配置；不下载新模型、不训练、不扩任务/模型/seed。
固定来源indices0..4，主计划5×3=15条。构造失败、错误、missing保留在计划和覆盖里，不换成其他更容易的来源。

已验收00：同源5条official/5条Remain全部成功，结束2026-10-09北京时间19:03:44。本阶段不重新调用VLA跑00。
准备仍构造00/10/01/11共20个state：00用于完整配对/恢复验证，不是主实验的新增episode。

## 3. 本轮立即执行：状态构造、独立回放、预览

冻结准备代码6e29f110b56a18ade63f401a1b6d8376fa9f95ba；
其benchmark/scripts/tests/configs与已审实现3a50f635b5eb7329386b381879ce53dab3bfbd46一致。
现有目录保留，不pull、不改实现，不覆盖00证据。

新输出（相对现有冻结checkout）：
data/stage03_basket_candidates_001/
reports/stage03_basket_replay_001/
reports/stage03_basket_preview_001.html
execute_logs/stage03_partial/

在/HUBU-AI096/zp/ICML/LIBERO-Remain-normal00-stage02运行：

```bash
/root/anaconda3/envs/peft-openvla/bin/python scripts/remaining_libero.py build \
  --tasks basket --scenes 5 --start-index 0 --split val \
  --out data/stage03_basket_candidates_001 \
  --settle-steps 80 --validation-steps 150 --max-candidates 24 \
  --velocity-tolerance 0.01 --robot-tolerance 0.002

/root/anaconda3/envs/peft-openvla/bin/python scripts/remaining_libero.py replay \
  --manifest data/stage03_basket_candidates_001/manifest.candidates.json \
  --out reports/stage03_basket_replay_001 --steps 150 --repeats 2 \
  --image-size 256 --velocity-tolerance 0.01 --robot-tolerance 0.002

PYTHONPATH=. .runtime/remaining_libero/venv/bin/python scripts/preview_remaining_candidates.py \
  --manifest data/stage03_basket_candidates_001/manifest.candidates.json \
  --replay reports/stage03_basket_replay_001/replay_report.json \
  --out reports/stage03_basket_preview_001.html
```

最多24个joint候选/来源，不因构造失败无上限搜索。仅原CLI构造/回放；无policy、无权重加载，GPU只用于渲染。
主检查：5个固定来源完整组、20状态mask准确、state/hash/初观测绑定、机器人与非白名单分量配对、动态150步审计、每state两次独立恢复。
正常最大回放20×2×150=6000控制步；构造含有界候选搜索。真实运行时间记日志，不用20Hz推墙钟。

技术通过不等于语义和剩余可执行通过。construction.legal=false原样保留，不自动盖“合法/可发布”章。

## 4. 基本语义/物理审查与独立执行诊断

Codex先核对每个10/01/11的完整状态/双视角：
mask符合预期；目标定义/物体关系成立；没有未授权重排、穿模或机器人相位变化；联合11摆放给出几何可行终态。初始遮挡/不完整视觉线索保留为挑战，不要求所有目标在起点清晰可见。桌面缺物体是可利用线索但非完成的充分证明，允许后续观察/试探核实。
原始完整指令不增加“跳过/已完成”提示，mask/predicate/object真值只用于评估，不能送给主模型。

对剩余可执行性，人工几何检查只给初步依据，不替代完成轨迹。
使用下节明确隔离的oracle-remaining-initial诊断：与主实验完全同一冻结10/01状态，只将初始未完成goal的catalog language交给同一模型，检查能否完成并保留初始成果。最多10条，固定5×2，不挑失败来源。
其joint成功可提供执行可行的正证据；失败仅记“未证实”，不能宣称物理不可达。需要另行脚本/人工执行证据时给X任务，不现场改评分救分数。
oracle诊断有真值选指令，不能混入主JSR/UIR，不是新方法的成绩，不冒充无oracle基线。

若执行可行性仍未知，保留该固定来源及所有证据，暂停将其策略失败归因于剩余目标重判；不得按被测模型成败筛除状态。正式评分发布前补齐证明或明确降级为探索性候选pilot。

## 5. X的最小代码任务005（实现前主VLA批不启动）

已有run默认迭代所有完整manifest episode，不能靠删00行、改legal或缩manifest绕过校验。
X提供：
1. 显式mask选择和dry-plan，完整源bank/replay仍完整校验；00明确not_selected，不伪装error/missing。
2. 原指令主pilot：固定10/01/11，expected15，恢复/动作/预算/评分沿用原实现。
3. 独立oracle-remaining-initial诊断：固定10/01，expected10，原始/有效指令及用途显式绑定；11不运行。源episode指令和完整goal specs不改，仅诊断的policy调用边界覆盖有效指令；不称oracle性能上界/因果证明。
4. 离线report/uir-template能处理主选择计划，主表JSR/UIR，所选expected分母/unknown覆盖正确；默认all与旧报告兼容且旧raw只读。
5. CPU/fake完整测试；逐项回应Codex。不运行GPU，不自行合并。任务004的版本记录修复仍单独审查，不借机改动作、RNG或指标。
6. 按005-A2实现pilot技术故障暂停/准确原因/资源关闭，保留expected与后续missing，success=False完整执行继续；保存本次实际reset返回且用于首次predict的白名单typed step0 NPZ，不复用构造参考、不额外render/step/reset、不改输入；记录真实query观测步与chunk执行映射，不增加预测或第三metric。

具体实现入口由X提出，Codex验收后写实可复制命令。本文件不伪造当前尚不存在的--masks/--instruction-mode参数。
接受提交后在新checkout冻结SHA，复用已验证runtime与同一state包；审查后源码再变必须重新验收。

## 6. 模型执行顺序与上限

条件：源bank技术通过、基本语义/物理核对、X005独立测试验收、模型/配置实际身份冻结。006非阻塞，不等初始可见性证明或专家观察轨迹。
先执行当前001固定来源的15条原指令探索性主pilot，直接观察模型如何看桌面、试抓、查篮子和调整剩余行动；初态0的前3条为本批技术检查，不额外重复，不增加独立样本。
再执行固定最多10条隔离oracle诊断，完整保存trace/视频与执行可行性裁决；诊断失败仅未证实，不要求同一VLA对照100%成功才允许测原模型，不筛主样本。没有执行证据时不作“失败由目标重判造成”的正式因果主张。
策略失败不是技术失败；共享接口/录像/初态恢复或实际step0记录错误由pilot程序显式暂停并保留已有/部分结果、停止原因和全部预定expected/后续missing，不仅靠盯日志或exit0，不能换index、换seed或现场修代码。旧默认all行为兼容。

10/01：H520+W150=670策略步，不因真值成功提前停止。11：W150策略步。
模型若没有显式STOP，照实记录；不将闭爪/小动作当STOP，不由GT评估器替主模型停车。停止任务操作可通过自然保持或必要安全收尾实现。
主最坏7450策略步、935个chunk查询；诊断最坏6700策略步、840个查询。最多25条模型episode，诊断与主分母完全分开。
实际model load次数以X方案登记；保持每episode seed7/reset队列，不以加载次数替代episode数。

本阶段不新增00策略episode、不跑全部任务/六模型矩阵、不训练、不开prompt scaffolding或学习gate/router。

## 7. UIR、交付与后续裁决

保留全步双相机20fps/stride1视频、step0 NPZ、每步目标/动作/STOP、queries/耗时/错误/源state/hash/代码/config/权重身份。
UIR由Codex/用户按冻结rubric审查完整视频，登记事件step区间、目标和理由；只有抽帧或无法保证全窗口审查时不得宣称完整审核，保留unknown/N/A。
依据实际预处理/crop后的信息、可用反馈和真实下一query机会，不将审核者全知状态/全幅视频视角当成策略信息。chunk中间反馈出现后，其余预排动作不等于策略已经拒绝更新；对齐后续query。当前OFT无显式观测历史，失败还可能涉及记忆/反馈利用，不断言内部意识或单一原因。
不修改原始run/summary/video；派生报告在新目录。本轮不把UIR=unknown换成0。
主表三行10/01/11，两列JSR/UIR，附固定分母、异常/missing和标注覆盖。诊断分表，步数/目标回退/必要性类别等仅作解释。

关键判读：
- 主失败、诊断成功：有依据进一步检查目标识别/路由，但仍不直接证明内部因果。
- 主与诊断都失败：不能直接归因“不会跳过”，先查状态/空间恢复与底层执行。
- 主JSR高且UIR低：如实报告已有适应能力。
- 主JSR高且UIR高：能完成但有不必要任务操作，标明发生阶段/目标。
- 任意未解决状态/技术/语义问题：不发布正式因果结论，不筛出“符合预测”的样本。

阶段结束由Codex在GitHub写Stage03总结，同时本地备份并校验SHA；源码由X实现，实验由Codex执行。

## 最新修订：2026-10-09 允许主动观察，撤销单帧可观察性停跑条件

5个固定来源/20状态构造、40次独立150-step回放全部通过，完整archive已本地核验；不是VLA结果。
初态0的RGB直接完成证据弱这一观察不变，但用户重申允许“简单观察和简单尝试后意识到”。Codex撤销因此暂停主VLA的裁决：信息获取/反馈利用正是被测能力，不将初始图像不清晰当作无效数据。
006改非阻塞行为诊断/标注规则，不要求X重摆成理想场景、改camera/crop或先交专家轨迹。保留当前001状态；005验收和基本有效性/身份核对后执行原始15条，主输入无mask、剩余提示或专家动作。
信息可获取性和oracle执行结果可辅助解释，但不是起点显眼或同一模型必须成功的筛选闸门；只有真实物理/恢复/任务定义错误，或充分证据证明允许交互下信息也不可获取，才另报有效性问题，不能从单帧遮挡推出。
主指标仍JSR/UIR。合理观察/试抓/空抓反馈不自动计UIR；对未完成目标反复失败不直接计干预，事件须绑定已满足目标/整体完成和无必要性完整证据，疑义unknown。此修订覆盖旧preflight1和006闸门要求，历史报告保留，未启动/改写任何旧VLA实验。
