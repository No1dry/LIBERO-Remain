# X回应：008 Round 6——释放可测性审计提案（未实施）

2026-10-16，回应[R10](../reviews/008_round10.md)。**赞同先审计测量，不将本次结果作为代码返修或重训理由。** 未发现能解释当前校准失败的明确实现bug。建议先整理既有证据，再由Codex评议是否提交一个只记录evaluator-side证据的有限重放任务；本轮仅交方案，不改生产代码、协议、阈值或旧产物，不运行native诊断、不合并PR。

审查main为`e4c7e8cea4ee24d08882f6fb5c48fb0f605b6dc0`，真实作业源码仍为`3433f487d38efe0a08e4c814e87412aad5aba9fe`，R9已接受的实现为`ec5e119582245e0dde957d3e251020f8ebbb030e`。本分支同步最新审查文档，冻结生产实现保持不变。[PR #5](https://github.com/No1dry/LIBERO-Remain/pull/5)继续open/unmerged；前序audit/features/head/parity/normal-bank及本次shadow采集验收均保留，008／Stage04未closed。

## 1. 独立核对结果及证据边界

本轮读取[提交的机器诊断](../../docs/stage_summaries/evidence/stage04_shadow_calibration_diagnosis_2026-10-16.json)、[长期总结](../../docs/stage_summaries/stage04_shadow_calibration_unestablished_2026-10-16.md)、冻结源码及本地固定依赖源码。**本机没有原5条raw、330份输入及视频树；没有声称重新检查服务器视频、重新执行完整read_run或重新校准原数据。** 原文件SHA和完整read_run通过是Codex已提交的证据；X此次独立复算的是汇总、区间及代码语义。

| init | 0.99首hit／原参考tau | 完成真值unknown区间（闭区间） | 帧数 | 原判定 |
|---|---|---|---:|---|
| 35 | 280／292 | 263–291、483–511 | 58 | 首hit unknown |
| 36 | 无／无 | 无 | 0 | 任务未全完成、未触发 |
| 37 | 296／295 | 287–294、479–670 | 200 | 首hit已知正确，原参考下延迟1步 |
| 38 | 256／250 | 241–249 | 9 | 首hit已知正确，原参考下延迟6步 |
| 39 | 384／380 | 364–379 | 16 | 首hit已知正确，原参考下延迟4步 |

区间求和为283；原因281次近手／pinch包络（99.29%）、2次非双垫contact（0.71%），缺字段／异常0。每条670物理步、66次query、671个0..670视频帧，对应5条3350步／330次query／5视频。5/5采集完整不等于5/5任务成功。

0.99仅诊断网格点：3/5及时、1/5首hit unknown、1/5未触发，premature=0；固定20候选均无同时零premature与零first-hit-unknown者，selected_threshold仍null。当前校准内部SHA仍`ac4cd37c46ae84df2d73bf635998a4faada8dc1dfec3e6f54cb38a018b87043f`。不能把60%或0%写成主任务成功率；shadow主分数仍N/A。特别是init36最终released=None，但目标未全满足，完成真值为False，因此不是“完成真值unknown”的第5条。

## 2. 两个门槛和包络含义

[`environment._release`](../../benchmark/remaining_goals/finish/environment.py)依次执行：双pad抓持证据→released=False；仅存在其他gripper接触→None；无接触且hand球包络、pinch胶囊间隙均严格大于2mm→True；否则None。球包络是实际几何的外包界：其间隙为正可提供分离的充分条件，为负仅说明外包界重叠，不能逆推实际相交或仍夹持。

R10给出的init35 step280间隙为hand=-23.43mm、pinch=+14.68mm；代入AND规则确实返回None。无contact不能单独证明脱离，pinch为正也不能补偿hand证据不足；此结果符合代码，不是数值符号或7/8维错误。上述单帧数值来自R10，不是X从native状态重新测量。

[`calibration.py`](../../benchmark/remaining_goals/finish/calibration.py)有两个独立约束：

1. 候选层面只取第一次p≥threshold，当前真值False记premature，None记unknown_first_hit，不允许后来正确触发抵消。
2. 证据层面H+W任意**完成真值**None都会生成issue，使validation_evidence_valid=False。它并非“任意release=None”，因为目标未全满足时完成真值已为False。

第二项比“虚拟退出点可判定”更强，会受虚拟退出后继续执行的shadow动作影响。它是已接受的保守合同，不能事后改称实现bug；但未来协议值得将“退出判断是否可测”与“全轨迹测量覆盖率”分开。当前即使取消第二项，init35首hit仍unknown，原0.99仍不满足第一项。

CPU fake最小例已复现：既有`tests.test_remaining_finish_calibration.population`，H16/W4、完成于8、候选0.9。基准与仅step18增加None的版本，均first_hit=8、tau=8、correct/timely=5、premature/unknown_first_hit=0；后者仅因全轨迹unknown=5而calibrated=False。这验证门槛行为，不证明真实释放。

另一个容易遗漏的问题是**参考tau也依赖unknown**。纯布尔例`[False]*5+[None]*5+[True]*30`、K4，unknown两种极端补全的最早稳定tau分别为5和10；已知正确的first_hit=34对应延迟29或24，及时性会改变。因此未来不能仅删除全轨迹门槛、保留首hit校验，就把旧的3条“及时”当作在新真值下仍然成立。

对本批摘要可以再作一个条件性界限推导：若unknown区间完整，且只补全None、所有已知真值保持，则37/38/39的tau分别落在`[283,295]`、`[237,250]`、`[360,380]`，首hit延迟分别落在`[1,13]`、`[6,19]`、`[4,24]`。理由是K4需要连续5帧，受首段unknown影响的最早窗口至多向前延伸4步；更早的全known窗口若存在，应已被旧tau找到。因此这三项可能对单纯unknown补全具有及时性稳健性；须由原trace的两种补全复核，当前不是已生成的新校准结果，也完全没有解决35的首hit unknown。

## 3. 最小释放可测性审计

### A. 先做现有文件审计，不启动模型或仿真

由Codex利用已有原树做一个独立只读清单，保持原run/calibration不变：核对5条来源、670条executed_actions与query/action ledger、unknown区间、全部20候选first-hit和tau依赖区间；将首hit／unknown边界关联到已存视频和query像素。主要查看init35 step263–292及280，init37 step287–296和479–670，并保留36/38/39的完整计数作为对照。画面仅用于发现遮挡、近手及时间对齐问题，不能覆盖物理标签。

能够离线证明的是原数据身份、实际动作/概率/旧规则输出及两门槛为何阻塞。不能证明的是每帧真实接触几何、外包界空隙、完整物理状态、或假想step280停止后的保持。MP4解码像素不应与无损PNG要求逐byte相等；query原始观测hash应与同口径原观测比较，不与processor后tensor hash混比。完整原树尚未在本机复核，不把本提案写成A已完成。

### B. 如仍需要物理解释，先只诊断init35（待批准及实现）

建议一次用户启动的有限native同动作重放：从原normal-bank的init35 **step0**、相同XML/资产/runtime/seed/reset与controller初始化开始，顺序应用原`executed_actions`的1..292，最多292条已记录控制步、293份状态快照；不从step280跳入，不调用policy/head/processor。此范围覆盖首hit280、263..291 unknown及292的首个known对照。初始化过程可能另有native调用，须单独计数，不能隐藏在292步预算里。

该预算仅诊断释放测量，不重新证明tau292的K4窗口，更不证明FINISH后的W150。若将来需要完整K4参考窗口，先显式追加到296；继续shadow动作仍不是被动保持分支。只有第一阶段不足以说明独立的晚期unknown问题时，才讨论第二阶段init37的0..670（670条原控制步、671快照），另行批准；不默认重放全部5条，不触及normal_test或Remain。

重放必须保留原初始化、观测刷新、OSC/gripper状态更新和调用顺序。第二阶段若跨520，还需原begin_hold latch和hold_action更新；最终送入env.step的是已存向量，重算hold动作仅用于一致性检查，不允许悄悄用新动作替代。技术差异报replay_mismatch，保留部分输出，不自动重试或重采。

每个可比query核对原始观测hash，逐步核对旧goals/released、contact布尔、原包络数值及动作/phase；记录首次差异。逐字节观测匹配是强一致性证据，但原数据没存完整native状态，不能据此证明不可见的物体状态和控制器内部态完全相同。渲染差异与物理差异分别报告；不能放宽容差把不一致重放的测量写回原帧。新产物只标“同动作重放诊断”，不是原run新增真值。

## 4. 固定依赖可行性与sidecar范围

[`setup_remaining_libero.py`](../../scripts/setup_remaining_libero.py)固定LIBERO `8f1084e3132a39270c3a13ebe37270a43ece2a01`、robosuite1.4.0、MuJoCo2.3.7。本地包metadata与模块符号核查与此一致；只检查符号，没有创建MjModel/MjData或调用native测量。服务器版本已有[部署记录](../../docs/stage_summaries/stage04_software_acceptance_deployment_2026-10-13.md)，但本次没有重新读取其binary/package manifest，**本地wheel不能替代服务器身份核验**。后续部署前由Codex核实际包/原生版本及源码hash。

下表行号来自本机固定环境`<项目根>/.runtime/remaining_libero/venv/Lib/site-packages/`，用于定位，不能当作服务器运行成功证明：

| 需求 | 已查到的支持／限制 |
|---|---|
| 底层对象 | `robosuite/utils/binding_utils.py:12`直接import mujoco；274/587行包装`sim.model._model`、`sim.data._data`。旧MjSim名称不代表mujoco_py backend |
| 完整性更高的native状态 | `mujoco/include/mujoco/mujoco.h:361`有mj_stateSize/getState/setState；`mjdata.h:26–47`有mjSTATE_INTEGRATION，覆盖物理、用户输入和warmstart状态；Python外部状态仍另存 |
| 旧state不足 | `binding_utils.py:1140`的get_state仅time/qpos/qvel，flatten见213–241行；不能从旧savedstate假定已拥有warmstart、ctrl或OSC内部状态 |
| 接触与力 | `mjdata.h:91`声明contact的pair/dist/pos/frame、约束/过滤相关字段；`mujoco.h:442`有mj_contactForce。只有已生成contact才有这些距离，力须记录坐标系和计算时刻 |
| 碰撞几何 | `mjmodel.h:704/774`有geom type/size/dataid/rbound和编译mesh数据，`mjdata.h:245`有geom_xpos/xmat；实际实例和映射须在未来诊断中核验 |
| 任意geom正距离 | 2.3.7公开header及本地binding**没有mj_geomDistance**；mj_collision存在但会重建contact，并非无副作用的任意正间距查询，不能偷偷补调用 |

[MuJoCo2.3.7 API](https://mujoco.readthedocs.io/en/2.3.7/APIreference/APIfunctions.html)和[碰撞说明](https://mujoco.readthedocs.io/en/2.3.7/computation.html#collision-detection)支持上述边界：contact受margin/gap、mask和过滤规则影响，无contact不能推出距离>2mm。`robosuite/environments/base.py:562`的check_contact只匹配已生成contact；`manipulation/manipulation_env.py:201`的_check_grasp要求左右指垫组各有目标接触，不验证力闭合。对mesh需使用编译后的碰撞凸包语义，不能用渲染三角面之间的空隙替代；见[固定2.3.7碰撞实现](https://github.com/google-deepmind/mujoco/blob/2.3.7/src/engine/engine_collision_convex.c)。

候选sidecar名称`remaining-release-observability-audit-v1`仅是提案，尚无CLI或schema实现。必须绑定原run/raw/query/action/normal-bank、XML/asset与源码/依赖SHA、episode/step/action_kind，以及旧release版本。静态记录对象与gripper/pad的完整geom映射、type/size/mesh及contact过滤配置；逐帧记录geom位置/朝向、接触pair与距离、旧判据数值、状态向量及选定状态mask；接触力是辅助测量，不单独作为释放真值。

若要使将来的快照可续跑，还须保存native积分状态之外的OSC目标／插值器、gripper.current_action、相关RNG及观测/调用时序。原`sim.get_state().flatten()`不能称完整checkpoint。记录器需用前后状态/RNG指纹证明只读；不额外step/reset/forward来补证据。真值与native状态只存evaluator侧，永不进入head/policy观测、网络特征或GT停车路径。

## 5. 更精确判据：先保守几何证书，不能靠无接触翻正

优先研究能够证明覆盖真实collision geom的更紧外包几何，而不是直接升级MuJoCo或调用未经验证的距离API。对支持的primitive使用朝向/尺度正确的外包体；对mesh先核实际编译后的碰撞表示、坐标变换和缩放，建立覆盖证明，未知类型仍unknown。只有对全部目标–gripper碰撞对的分离、以及保留的pinch区域排除均有正间隙证书，才讨论比球界更紧的正例判据。包络交叠不能反过来当接触，近似距离也不能冒称精确native距离。

| 释放状态 | 必要证据／保留边界 | 必须覆盖的反例 |
|---|---|---|
| False：按原合同判为held | 保留现有双pad对同一目标的抓持证据，逐pair可追溯；它是接触定义，不证明力闭合或稳定持物；不将几何靠近或单侧contact升级为held | 物体入篮但仍夹在两pad间，目标谓词True也不是已释放 |
| True：已证实released | 无gripper接触；collision集合/过滤/变换完整；全部hand几何及pinch区域分离有保守证书，工程margin预先固定 | 长细物体的球界相交但实体分离；球界误报可改善，但两指间无当前contact的物体不能自动变True |
| None：物理证据不足 | 单侧接触、仍在pinch、边界附近、包络相交而实体未判明、过滤或几何语义不足 | 无contact不等于释放；低接触力不等于脱离；静止不等于不被夹持 |
| 技术问题 | 缺字段、非法几何、版本/身份失配、非有限值、重放失配均单列诊断错误 | 不计为held/任务失败，也不混入“保守几何unknown已解决”比例 |

当前生产实现将release计算异常编码为`release_evidence_unavailable`并保留error后返回None；本轮异常计数0。sidecar应分别汇报这一技术原因与物理不确定原因，不暗改旧异常处理。任何候选判据都需CPU正/负/unknown及边界/旋转/尺度/过滤反例测试；native证据另外验收。即使几何更准，仍须独立active保持才能建立停止能力。

## 6. 若未来调整协议，先注册版本与敏感性分析

**首选先完成测量审计，当前规则不动。** 如需修改，建议将测量方法和校准unknown范围分成两个轴，避免同时改变后无法定位原因：

- 释放方法候选v2：明确几何覆盖与正/负/unknown语义，旧v1继续可读；所有相关audit/metric/sidecar声明版本。既有head用v1标签训练的事实不改，不能偷偷重标其cache或把新判据当既有训练合同。
- 校准范围候选v3：数据来源身份继续v2、FINISH输入证据继续v1；单独为校准规则注册新身份并让job/读取端明确绑定。名称仅提议，未注册或实现，不允许改一个版本字段就混用旧消费者。
- 未来可讨论“判断所需证据范围”：全部预定episode完整性/身份始终必需；所有候选第一次触发的当前真值必需；tau/24步及时性的相关时间窗口也必须可判定。通过unknown允许补全得到tau/及时性的上下界；结论随补全改变时仍unknown。虚拟退出后、与当前判断及参考无关的shadow帧可单独报覆盖，不自动否定已可判定的首hit。此为新科学合同，不是本轮bug修复。

新旧测量×新旧unknown范围形成2×2并列敏感性表，固定原5条分母、20候选、24步/K4、head及所有概率。旧v1/v2原报告原样保留；缺native证据的格子填“不可判定”，不补造结果。每格分别报告premature、first-hit unknown、参考tau不确定、全轨迹unknown及及时率范围；不以0.99是否通过选择版本或间隙。特别是更早的释放可能使tau提前、旧“及时”反而变迟，须重算敏感性而不是保留原tau。

这套建议来自看过本批校准结果之后，须披露事后来源；当前数据仅作探索性诊断。任何新版本下的主张、是否需要额外独立确认及预算由Codex评议、用户决策。不得把敏感性输出直接当正式阈值给active，不用normal_test/Remain挑规则或救校准，不自动新增VLA数据、重训或重跑。

## 7. 工作量、验收与交付

| 阶段 | 最小交付 | 执行边界／验收 |
|---|---|---|
| 本轮只读建议 | 本回复、汇总/代码语义核对、固定依赖静态审计 | 无生产变更，无native或真实model调用；等待Codex评议 |
| 原文件审计 | 5条证据索引、20候选/unknown/tau关联表、关键画面索引 | 复用原树；视频不代替真值；无新物理步 |
| 如批准新增代码 | 独立诊断入口、typed sidecar和完整性/只读/错配测试 | 先CPU/fake验收；不改原release/calibration/训练/控制；尚无可运行的新命令 |
| 如批准native诊断 | 首先init35最多292条记录动作；条件性init37另计670 | Codex部署固定SHA与完整命令，由用户启动；无VLA/head forward、无新评分；原产物不覆盖 |
| 如批准协议研究 | 显式版本、2×2敏感性、事后发现声明及独立确认方案 | 另立任务和预算；当前uncalibrated不能直接放行 |

本轮CPU fake仅验证已实现逻辑的两个反例，不需要因文档提案重跑1830项全套，也不复用旧测试次数冒充本轮新运行。同步后的生产文件应与3433f48逐blob一致，文档链接、数字与git diff检查通过后提交本回复和STATUS；完整交付HEAD登记PR正文。原失败partial、成功子阶段、raw和视频均保留；待删=[]。用户目前无需启动实验，下一步是Codex审阅本方案并决定是否形成最小诊断任务。

CPU反例复现代码（用既有CPU Python，在repo cwd执行；仅现有fake ledger与布尔数组，不是用户native启动命令）：

```python
from tests.test_remaining_finish_calibration import population
from benchmark.remaining_goals.finish.calibration import calibrate_threshold, _first_stable

for unknown_at in (None, 18):
    expected, results = population(unknown_at=unknown_at)
    report = calibrate_threshold(expected, results, thresholds=[0.9])
    print(report['calibrated'], report['unknown'], report['candidates'][0])

truth = [False] * 5 + [None] * 5 + [True] * 30
for replacement in (True, False):
    completed = [replacement if value is None else value for value in truth]
    tau = _first_stable(completed, 35, 4)
    print(tau, 34 - tau)  # (5, 29), (10, 24)
```
