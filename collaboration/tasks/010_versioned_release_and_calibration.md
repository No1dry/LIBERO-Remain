# 010：版本化释放测量补充与决策相关停止校准

2026-10-16，open。用户明确同意“版本化修订”：更紧保守几何证书、只核验停止判断及完成时机所需证据；旧结果不改、不重训，另采5条新版普通校准，模型轨迹总预算30→35。X现在实现代码/CPU-fake，不再交一轮纯提案；真实采集仍由用户启动。

## 0. 基准、原因与不可变项

[009真实结果](../../docs/stage_summaries/stage04_task009_result_and_revision_2026-10-16.md)已验收：292/292动作、293快照、37原观测全部匹配，0 NN调用。step280旧球界-23.43mm，但全部24番茄collision geom与全部5 hand geom在world-z有≥14.72mm分离证书，旧pinch净间隙+14.68mm，无hand-target contact。这证明该帧球包络过松，不是给所有unknown翻True的依据。

从已审2c6dc4c20a12b4b894a3919d79b9bf810648332d为功能基准。009范围已完成，PR #6可由X按既有accepted合并，保留最新main的结果/010文档，然后另开010分支/PR；Codex不代merge。禁止覆盖旧代码实验目录和原始产物。

必须保持：原SOG10 OFT/base/LoRA/action/视觉/proprio projector、head权重6636f713…及其v1训练label合同、runtime/crop/seed7、56-token FP32特征与8维proprio/8×7动作字节路径；不重做HDF audit/features/head训练/真实parity/normal-bank。model.py/training.py/oft.py及原adapter若非必要不得改；新真值/几何/版本信息绝不进入policy/head输入。H520、W150、chunk8、K4、24步及时窗口、20候选阈值和固定来源组不改；不加VLM或人工标注主分数。

这是明确新科学合同，不伪装成原代码bug修复。旧calibration ac4cd37c…保持calibrated=false、threshold=null，原5条v1 shadow只是探索/问题发现，不因新方法重写成功或补成已校准。

## 1. release测量v2：仅保守分离证书补充

v1默认/读写保持；v2显式opt-in。先完整保留v1顺序：双pad抓持→False；其他gripper接触→None；原球/夹持包络均>2mm→True。v2不得将v1 False改True，不得将原known True改Unknown；原unknown不默认负例。

**第一版只做如下补充，不研发GJK/任意精确距离/新native API：**

仅在v1为None且reason=近手包络、dual_pad_grasp=False、any_gripper_contact=False时，保留原pinch_capsule_clearance严格>0.002m为必要条件；然后尝试world x/y/z三个预注册轴上的**整个对象collision集合与整个gripper contact集合（含两pad）**分离证书。

对每个轴：对象所有geom区间取union的[min,max]，hand所有geom亦同；gap=max(hand_min-object_max, object_min-hand_max)。任一轴保守gap严格>2mm即可证明hand几何分离。选最大正gap，tie按x/y/z固定顺序，不根据seed/模型结果选轴。仅在无contact、pinch排除且证书齐全时返回True；否则维持None。

支持范围先限当前任务实际需要的box(type6)和mesh(type7)：
- box投影半径=sum(abs(world_rotation轴行)*native halfsize)；world center取geom_xpos。
- mesh用**编译后的mesh_vert**按geom_xmat/xpos变换，对线性轴投影取全部顶点min/max；它覆盖collision凸包，不能拿渲染面/原始文件bbox或mesh的size字段冒充精确几何。
- 未支持但合法的type/无法给证书→None并报告coverage；缺字段、身份失配、非法引用或非有限值单列measurement技术问题，不能算held/策略失败。
- 碰撞过滤、geom组完整性、姿态和尺度必须核验；不得通过禁用碰撞、改变margin/gap/mask或只选有利geom造正证书。当前margin/gap均0；对不支持的非零过滤/间隙情况保守不新增True，明确理由。
- 新计算纯读取，无额外step/reset/forward/collision/controller.update/render或RNG消耗；缓存若使用须绑定当前model/XML，所有reset/示范XML换模型时失效，不能复用旧ID。
- 新证书是保守轴向分离**下界**，不是精确最短距离。保留旧sphere/pinch/contact证据及新axis/区间/极值geom/模型身份，足够离线重核；不能只存certificate=True。

可复用009只读几何数据思路，但不能把整套重放/全checkpoint系统塞入每步控制。证明依据为固定MuJoCo2.3.7[collision support](https://github.com/google-deepmind/mujoco/blob/2.3.7/src/engine/engine_collision_convex.c)的compiled geometry，不升级依赖。生产只支持已证明的primitive/mesh，不承诺任意新任务几何。

## 2. 新校准规则：first-hit与tau不确定区间

独立显式版本，保留旧全轨迹unknown门槛算法可读/可复算。新规则不把无关时段的completion-unknown自动否决整条，但完整轨迹/identity/输入/视频/缺失/技术问题仍全部验证，固定预定分母5；不删坏样本。

保持每候选逐条取第一次p>=t。当前真值False→premature；None→unknown_first_hit；True→correct。无触发→not_triggered，不因任务未完成擅自替换来源。

对goals+released形成的三态完成truth，仅对None做两端假设，所有known False/True不动：
- tau_low：None全True后按原_first_stable(H,K4)求最早稳定起点；
- tau_high：None全False后同法求起点。
这是假设区间，不生成新物理标签；K4为4区间/5观测，不能把已知未完成的前4帧倒推为True。
- 只有first-hit current=True且所有可能tau都使0<=f-tau<=24时，计**robust timely**；双端有限时等价tau_high<=f<=tau_low+24。
- 如果两端均无参考，timely=False（无稳定参考）；如果区间完全排除及时，则timely=False且不是新premature。
- 若timely结论随补全改变，或一端无稳定参考而无法证实结论，标timing_unknown；不要只取有利端。允许更严谨的等价区间实现，但须交证明/反例。
- 未触发的timely已确定False，无需为无关tau不确定单独否决它；首hit False/None先按上述规则处理，不能靠tau/后来触发抵消。

候选可行性：premature=0、unknown_first_hit=0、**timing_unknown=0**，且预定数据完整无技术错误；在可行候选中最大化robust timely数，同分取较高阈值；有用候选仍须robust timely>0。无有用候选如实capability_not_established。网格仍0.05..0.95步0.05及0.99，不加0.995/0.999来救通过。保留旧selected_threshold=null。

输出每条first-hit、current truth、tau两端、delay区间、timely真/假/unknown及原因；全轨迹unknown覆盖仍作诊断，不藏掉。不要把“新候选阈值冻结”写成普通stop能力已建立，独立active仍必需。

## 3. 版本、绑定与旧兼容（一次打通消费者）

请在交付列实际版本/字段/读写表，不只改一个schema常量：
- release v1/v2方法、calibration legacy/new规则分别显式标识并绑定hash；可采用evaluation/measurement contract对象，具体命名由X定，不因名字返修。
- job/config→dry-plan→environment→trace/objects/evidence/run→metrics/report→calibrate→active reader全链路一致分派。旧artifact缺新字段只能进入明确legacy路径，不能按新版解释；若结构白名单需新schema则显式分版，不能删校验来混用。
- 旧PROTOCOL/结果/校准/metric/raw/cache/head读写与重新校验保持，旧hash/记录原样；旧默认config和009 replay默认仍v1，不无条件添加新truth字段破坏旧严格对照。
- head仍用原v1保守标签训练：feature/cache/head版本、weights/implementation SHA都不重写，不全局替换LABEL_CONTRACT。evaluation contract与training label contract分开声明，不能因此拒绝合法冻结旧头或假称它已按v2重训。
- active必须校准valid、头/来源/测量/校准规则版本完全一致；拒绝旧未校准报告、不同head/role/方法/敏感性-only派生报告。不能fallback默认0.99。
- 物理LIBERO/XML/原normal-bank初态不变，observer版本不能伪装成换环境或篡造旧fingerprint；若现identity层有冲突，显式区分physics与measurement，不要偷偷重建15个来源。
- action/FINISH控制及W150 hold不读取GT决定停止/开爪。新测量只用于evaluator评分与离线校准，不能影响预测/动作或shadow执行步数。

## 4. 新5条shadow及敏感性，预算明确35

沿用已prepared bank。新正式校准只用official-init35..39，新opt-in v2测量+新规则，输出全新目录；40..49仍10条独立normal_test，Remain0..4×10/01/11仍15条。模型、head、输入、初态和seed不变。旧5条已经用掉，新增5条由用户明确批准：**5旧+5新+10normal+15Remain=35，最坏23450模型rollout物理步**；audit/features/parity及292诊断另计。新预算计划/日志/文档明确，旧30条原计划和旧run不改写；不自动追加其他rollout或训练。

在这**同一批新5条轨迹**上记录足以离线复算的v1/v2测量事实与新证书（静态geom/mesh和必要动态位姿可typed保存一次/按需保存），不会为两套observer重复跑模型或物理。保持head输入原白名单，不把这些真值/证书放进网络。避免每步全checkpoint，记录只需足够重核判据/证书和版本。

给出release v1/v2 ×校准旧/新的2×2派生敏感性表，固定相同5条分母、head概率、20阈值/K4/24步。缺证据的单元格写不可判定，不补造旧5条的v2真值；已有009只有35号0..292，不代替新5条正式采集。所有派生结果标来源与sensitivity-only，不作为active正式阈值；正式输出仅按预注册“新测量+新规则”从新5条数据生成。

明确这是看过旧pilot后修订；新5条同来源是校准开发而非独立泛化证明。10条normal_test和Remain仍未使用，不能用它们挑方法/阈值。先新shadow→离线校准冻结→10normal active独立停止验证→15Remain，每个真实阶段用户单独启动；任何失败先分析，不自动继续或改模型。

## 5. 自动评价仍保持少量主指标

主表仍只有合规FINISH成功率（百分比+n/N）、原已有延迟/失败原因/覆盖诊断。FINISH瞬间所有目标+released，初始成果全程保持，FINISH后W150目标保持，sticky错物稳定入篮K4这些要求不放宽。测量证书/版本/unknown分布是取证，不另加一堆论文主metric。Shadow主FINISH=N/A，不写0%；技术错误/缺失/不可判定不能伪装策略误判。

## 6. CPU/fake与交付（不跑真实native/模型）

需要实际通过的回归：
1. 旋转/平移的box及compiled-mesh投影、负坐标、尺度、compound union；球界负但分离证书正、球界正保留；轴顺序/tie确定。全部geom而非只最有利对。
2. held False、单侧contact None、pinch未清除None、无contact但无证书None；未知类型/过滤/非法值明确分流，不凭静止、开爪或低力判True。
3. 与009 step280数据的只读CPU几何核对：番茄/hand world-z下界0.014728840702336488m（保守14.72mm），旧球-0.023432828897614985m，pinch+0.014681542347722397m。可以外部fixture路径复核，不把57MB native原树、权重或大型mesh塞GitHub；CI用合成/小型反例，不mock掉几何算法。原case只诊断，不改旧raw。
4. 旧calibration仍复现uncalibrated；new first-hit首False/None/多次cross、非触发、tau边界/无参考/一端无参考/±24/unknown在无关W段、known False不可补真、timing_unknown候选不可选。新规则不把一端有利当鲁棒。
5. 默认legacy及所有旧schema/hash/头/cache可读；新版完整env→record→read_run→calibrate→dry-plan→fake active链路。方法/头/来源/版本错配及未校准/sensitivity artifact拒绝。
6. 修改GT/observer输出不改变policy输入、动作/FINISH应用时序或hold；NN及原action路径byte diff说明。记录几何不耗RNG/不推进native。
7. 新/旧方法双测量及2×2表的identity/不可判定边界，敏感性数据不可冒充新主阈值；35预算与固定5/10/15角色，无额外模型作业。

可用tiny CPU模型fixture作为软件测试，不加载研究VLA/head或创建真实MjModel/MjData。--help/dry-plan/离线统计应无真实native/NN。报告新增/受影响/FINISH全套passed与skip原因，不用旧次数冒充新测试；不因风格返修，不把科研效果作为代码验收门槛。

独立PR交010_round1、实现/最终SHA、版本表、最小diff、CPU证据、新配置、实际可解析完整plan/shadow/calibrate/normal/Remain命令。Codex验收后才部署新目录/配置并给用户唯一下一真实命令。X不合并010、不改旧结果、不自跑真实作业。若效果不足如实报告，不自动扩数据/调head。

[009真实验收/授权记录](../../docs/stage_summaries/stage04_task009_result_and_revision_2026-10-16.md)。010 open；原校准未建立，Stage04未closed，精确待删=[]。
