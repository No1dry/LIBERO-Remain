# Plan 4：统一FINISH接口与停止校准基线

初版：2026-10-12；修订：2026-10-14。阶段：Stage04。007软件已验收并部署4f76f49，用户source0_11四步真实预检通过；尚无head训练或新模型成绩。用户已明确批准两个来源域方案A，由008实施数据身份／审计改动后再启动真实audit。  
分工：用户确认并启动真实实验；X实现代码与CPU/fake测试；Codex研究需求、非实验数据／文件准备、建议式审查、校验部署、完整命令及结果审查。

## 1. 为什么做这一步

目的不是用FINISH补救低分，而是给benchmark提供明确的任务结束接口，并建立已具备普通停止能力的基线。研究问题仍是：外部提前完成任意部分任务后，策略能否重新确定剩余目标，保留已有成果并合规结束？

论文希望检验的命题为：即使具备普通任务的停止能力，外部预完成状态仍可能使剩余行动或结束判断退化。不能预先要求基线失败，不能按失败筛来源或调指标压低分数。

原始OFT没有任务级FINISH接口，不能在新结束指标中把它的“不支持”写成0%并据此证明缺陷。它保留为旧JSR／动作现象参考；正式主基线是原动作策略加普通停止校准。原始模型、校准基线和未来方法的名称与训练范围分别披露。

## 2. 本次权责（覆盖旧计划中的未来职责）

- 用户：确认并亲自启动真实数据审计／恢复、特征、训练、校准、parity和eval，决定继续或暂停；命令自动记录日志与原始产物。
- X：修改benchmark与模型适配代码，CPU/fake单元测试，GitHub提交与交付说明；不启动真实模型或实验。
- Codex：研究设计、详细需求、非实验下载／文件与来源清单准备、静态/CPU-fake审查、部署与完整命令、读取结果后归档；不自主启动、追加或重跑真实实验，不自动创建后台监控。
- 软件单元测试不等于科研实验；CPU/fake测试可以由X与Codex做，但加载真实VLA、真实仿真、真实数据训练由用户运行。
- 审查只以明确错误、协议违反、危险控制、证据／身份错误和关键已约定功能缺失作为阻塞。命名、风格、可合理替代的工程设计、额外功能或未经验证的性能建议不作为返修理由。一次集中列出问题，避免逐轮增加需求。
- 训练质量或正常停止能力未建立是科研结果，不自动等于X代码错误。需由用户决定数据／训练调整，而不是无限返修代码。

## 3. 代码基准、范围与不变项

Stage03实验冻结04508dc，PR #3已由X合并为869f409。007/PR #4软件修复的已审head为4f76f4917a9174fc5b80ef83e3cf21eaf053c98d，部署已核；OnTheGroundPanda误拒绝已修复，用户同一11四步预检已通过，旧38失败保留。

008是用户批准A后的新需求，不是007返修。X先按既有accepted授权合并保持已审实现的PR #4并登记merge，再从含该实现与最新规则的main开独立008 PR；Codex不代合并实现。仅文档冲突保留最新分工、裁决和计划，不覆盖旧raw。

本轮只做LIBERO-10 basket、当前SOG10 OFT及小型finish head，不扩任务／模型，不端到端微调VLA，不加剩余目标提示、router、记忆或VLM裁判。

原动作模型、LoRA、action head、视觉／proprio projector全部冻结且保持eval。原指令、输入传感器、crop、动作解码、8步chunk和policy seed7保持；不为11设置最小行动步数。训练接口可称finish head，不需向词表或输入插入新token。原实现中的EOS不是任务结束信号。

旧manifest、状态、代码实验版本、raw、JSR/UIR及Plan3结果不改写。新协议独立入口和schema，旧默认行为保持。现有001仍是候选pilot状态，不能自动升级为正式发布bank。

## 4. FINISH协议v1（本次默认实施规格）

### 4.1 时间与查询

所有mask统一决策预算H=520控制步，退出后保持W=150控制步；20Hz下分别26秒和7.5秒仿真时间。11也有正常观察／尝试预算，不要求t0立即FINISH。此协议与旧11只运行150策略步不同，成绩不得混用。

仅在真实policy query边界判断：t0开始、动作队列耗尽时重新query，chunk8。H处允许最后一次query；先处理active的有效FINISH，否则标TIMEOUT。H后的候选动作不能执行。若未来H不整除chunk，最后chunk按预算截断，不凭GT在chunk中途停车。

active在f<=H发FINISH，实际物理步数f+W；超时实际物理步数H+W。退出后不再query，只执行safe hold并记录真实物理。timeout是预算事件，不是模型FINISH；finish_step与timeout_step互斥。

### 4.2 决策与证据

推荐worker返回已声明的finish-v1对象，包括候选8×7动作、finish logit/probability、固定阈值与head_decision。具体类型可由X合理实现，但必须区分候选动作和实际执行动作。

- active：p>=threshold时应用FINISH，不执行该query的候选动作；不管GT是否正确，都执行退出并事后评分。
- shadow：同一head仍打分并记录，但不应用FINISH；原动作照常执行，到H按TIMEOUT退出。它是诊断，不是主FINISH成绩。
- GT、mask、step、H、源编号、label及未来帧不得作为head输入；完整原指令不改。
- 记录head_decision和applied_decision；两者在shadow和deadline处可能不同。
- 每query绑定实际观测步、输入hash／实际裁剪画面引用、候选／接受／执行区间、head及阈值身份。不额外predict来取证。
- head缺失、NaN、版本不符等报技术错误，不能静默退回无停止模型。

### 4.3 退出后的物理保持

FINISH或TIMEOUT后都继续真实物理W步，记录hold cause=finish或timeout。不冻结sim，不用env.done结束保持，不自动释放来“修好”提前FINISH。

hold控制器按当前proprio／控制状态维持姿态与夹爪，不能依据目标真值改变控制。沿用已有环境的显式hold contract思想；不能假设“零位移＋开爪”普遍安全。X声明方法，提供CPU测试和用户运行的真实预检命令。

## 5. 自动评分（独立版本）

主表暂只保留一项：合规FINISH成功率。结束延迟及失败原因作诊断，不继续依赖逐条人工UIR作为主评分。

S_i=true需同时满足：

1. active的FINISH在0..H产生，而非timeout、oracle或未支持接口；
2. FINISH决策对应的状态中全部目标已满足，目标对象已脱离夹持；不是执行hold后才补成成功；
3. 初始已完成目标在整个0..f+W窗口保持；
4. 全部目标在f..f+W保持满足；
5. 整个窗口无明确禁止的错对象稳定投放。

合规FINISH成功率=100%×成功数／固定预定episode数。报告百分比＋n/N、有效覆盖及technical error／missing／不可计分数量，不将其伪装成策略误判。不因政策失败换样本或缩分母。

禁止投放：本篮子任务中，初始位于篮子外的非目标可移动物体，新增稳定入篮且已释放。篮子／桌子不是额外投放对象；初始就在篮子里的其他物体不要求清除。单次接触、短暂穿过容器区域或观察动作不直接判错误。确认事件后不可因后来移出／完成目标而擦除。

稳定确认默认先采用4控制步，作为显式版本参数；测试1／4／8步敏感性，不能依据测试模型表现调整默认。释放判定须结合真实接触／夹持信息；疑义不得默认为已释放，算法和缺失处理写入版本。规则不识别所有语义冗余，不设置“最多两次试抓”等任意次数上限。

自动原因可多标签：premature_finish、no_finish_timeout、unfinished_goal、goal_regression、forbidden_placement、unstable_after_exit，以及独立技术错误。wrong-object违规发生在FINISH前，FINISH不能撤销。

结束延迟：从首次满足目标且已释放、并通过短稳定确认的区间起点τ算f−τ；这是事后GT诊断，不进入策略。11的有效预完成状态τ=0。确认使用未来帧只可用于离线证据，不可给head。若正确FINISH后的保持确认了稳定区间，参考区间起点不晚于f，不人为制造负延迟。提前FINISH、timeout、未完成和缺失明确分列；不能只统计及时停止者而藏掉未停止样本。延迟给步数／仿真秒及适用覆盖，不称全部是冗余时间。

## 6. finish head及训练数据

默认特征：原L1 action head使用的56个action-token hidden states，沿token维均值pool成D维；不得把EOS、prompt或视觉patch混入该切片。复用同一次原forward，不插入token、不改变attention、不做另一套动作预测。

默认小head：LayerNorm(D) → Linear(D,128) → GELU → Linear(128,1)，无dropout；sigmoid后判FINISH。X可提出等价的更简单工程实现，说明差异即可，不为风格返修。

仅优化head，特征detach；使用BCEWithLogitsLoss，pos_weight只按training负／正样本数计算，无正例或无负例则报告数据不足而不训练。记录原网络参数／权重hash、feature接口版本与dtype。默认seed7、AdamW、lr=1e-3、weight_decay=1e-4、batch128、最多50 epochs。checkpoint按普通validation BCE最低选取，同分取较早epoch；不查看Remain结果挑checkpoint。该配置是首轮有界起点，不保证效果，不自动多seed／多模型扫参。

标签从正常00示范／训练来源的普通rollout物理证据生成：当前目标全满足、已释放并确认稳定为正；未完成／只完成一项／暂时入篮仍夹持为负。轨迹最后一帧、is_last、t/T和停止动作不能代替标签。无足够物理证据标unknown并披露，不造正例。失败／停滞负例有数据则加入；没有时明确覆盖缺口，不伪造。

正例稳定确认指在同一退出保持协议下从该saved state做K=4步被动保持确认；不是让示范未来任务动作继续，再用它是否撤销目标给当前状态贴标签。生成前保存当前真实观测，head只看该当前观测；标签确认分支不替代输入，不回写源轨迹。这属于用户执行的标签审计，不是在eval在线增添额外step／真值许可。可复用已存等价被动保持证据，否则缺确认记unknown。

可在正常轨迹中出现自然中间partial状态；禁止把外部编辑的10/01/11测试变体拿来训练或校准，再声称泛化。特征只含原合法观测和原指令；标签／分组／时间仅存metadata。

### 两个来源域划分（2026-10-14用户已批准A，替代初版统一source-index前提）

公开HDF的演示与official init逐一物理来源映射未证明。用户明确选择复用公开普通演示、将head轨迹域与评测init域分开；不通过demo编号、最近邻或假provenance建立旧映射。

| 域／用途 | 固定组 |
|---|---|
| HDF head_train | demo_5..demo_34，30条完整trajectory |
| HDF head_validation | demo_35..demo_39，5条完整trajectory；用于val BCE与32不同输入parity |
| HDF head_unused | demo_0..4及demo_40..49，15条不参与head，保持原规模不按成绩替换 |
| official init normal_calibration | init35..39，5条普通00 shadow，冻结阈值 |
| official init normal_test | init40..49，10条独立普通00 active |
| official init Remain | init0..4及这些来源全部编辑变体保留评测，主15条10/01/11 |

HDF编号只选择文件中实际group名字，不代表采集seed或eval init_index。来源键需domain+实际文件SHA+group/index；两个域相同数值不等于同源。head_validation与normal_calibration不得再共用一个歧义validation/source_index身份。

保留轨迹级train/validation互斥、重复state/observation跨组检查、不直接用编辑测试输入训练头；source/domain/label/time仍只metadata。HDF正负类、actual XML、layout与真实K4物理标签审计不能省略。组不存在／标签不足等仍insufficient，不自动重选或采新rollout。

明确限制：无法证明新增head训练示范与official eval的物理祖源完全独立，不能以不同namespace冒充严格同源holdout；冻结SOG10未见该来源同样未证明。此pilot主张是显式轨迹分组＋不直接使用编辑评测样本，原更强来源隔离主张收窄。若将来需要严格源级泛化，另审批可追溯采集，不在当前预算自动增加。

008统一audit/cache/head/calibration/job/parity身份消费者，旧统一source语义仅保留历史读取，不能隐式与新合同混用；具体验收见[008任务](../../collaboration/tasks/008_finish_data_source_domains.md)。这只改数据身份/分组，不改模型、标签、停止控制、指标或H/W。

## 7. 校准与普通停止能力检查

阈值校准仅使用official init域的normal_calibration=35..39，用户运行5条shadow普通00；它与HDF域head_validation=demo35..39是两个明确不同的组。head epoch只按HDF head_validation BCE选，不能用normal_test或Remain挑epoch/阈值。

阈值候选0.05..0.95（步长0.05）及0.99；先要求validation未完成阶段观察到的提前FINISH为0，再最大化完成后24控制步内的正确FINISH比例，同分优先更高阈值。24步是3个query周期的首轮校准尺度，必须显式声明，不从测试结果倒推。若无法建立正常停止能力，输出能力未建立，不用高分类accuracy冒充；科研调整由用户决定，不自动返修X。

每个阈值逐episode按真实query顺序取首次p>=threshold为虚拟退出点，只判该点的全部目标／释放状态；首次误停不能用后来高分抵消。候选及时FINISH率使用固定validation预定episode分母，未完成／未触发算未命中；unknown／关键证据缺失单列并停止已校准声明，不能删掉救阈值。shadow只能提供离线候选退出，不能用其继续执行的后续策略轨迹冒充停止后的hold稳定；物理合规仍由独立active测试验证。

独立normal00 test拟10条active。报告完成能力、提前FINISH率、完成后及时FINISH比例、退出延迟及覆盖。建议沟通门槛为至少90%及时正确停止、提前误停不超过10%；10条仅pilot，不能当成统计充分证据。门槛不是代码验收条件，不允许用test集重新调阈值。

## 8. 用户执行顺序与首轮上限

所有真实步骤独立命令，由用户决定何时运行；不得自动串联进入下阶段。

1. 纯配置／路径／身份dry-plan：不加载VLA、不创建仿真。
2. 真实data-audit与标签生成；缺来源或标签证据不足先报告。
3. 特征导出及head训练（首轮单head、最多50 epochs）。
4. validation shadow正常00：拟5条；校准阈值并冻结artifact。
5. 真实模型shadow一致性检查：固定32个不同的HDF head_validation合法观测输入，核对原动作与新增只读分支动作。
6. 独立正常00 active：拟10条，能力检查。
7. 当前001固定0..4的10／01／11 active主pilot：15条，不挑失败来源。
8. 用户需要更强配对证据时，可再运行同15条shadow诊断；默认不自动追加。

默认模型rollout上限30条（5+10+15），最坏30×670=20100物理控制步；可选配对shadow另15条。特征抽取／真实一致性前向不是这30条rollout，数量、模型load次数和预算须单独在dry-plan披露。数据不足时不自动采集新VLA轨迹。官方HDF已由Codex下载核SHA；本方案不新增VLA采集rollout，标签/特征/parity费用仍另计。

正常00测试需要新来源状态与配置，X提供准备命令和准确源身份；现有001测试bank及旧实验不改。不能把正式基线的不支持接口或数据缺失算成重判定失败。任何主成绩发布先验证停止能力、数据划分与真值隔离，不以主测试低分为门槛。

## 9. X交付和建议式审查

GitHub任务：007实现已软件accepted；当前数据域新需求为collaboration/tasks/008_finish_data_source_domains.md。X在独立PR一次性交付接口／代码、CPU测试、配置、完整命令和未完成项。核心验收只针对已约定功能和明确错误；扩展任务、VLM裁判、额外图表和性能优化不在本次范围。

需有：独立版本读写／复算、active与shadow分离、deadline／hold证据、无GT门控、参数冻结／原动作一致性、分组与标签可追溯、旧路径兼容、CPU负面测试。实际模型、head效果和真实hold的结果由用户运行后审查，不能以fake测试证明。

## 10. 部署与完整命令交付

Codex验收后上传冻结源码到新的服务器目录，不覆盖旧checkout、runtime、checkpoint或原始数据；记录source commit、源码／配置SHA及部署回执。已知工作根目录为/HUBU-AI096/zp/ICML，旧stage03目录仅用于复用已核实资产；部署时只读确认路径和依赖，不凭记忆更换版本。

Codex交用户本地runbook，逐步给出实际存在的入口、准确python／cwd／参数／输入／新输出路径、日志重定向、退出码与检查方式。依赖安装／真实预检若需要，也给用户命令，不代跑。

007的13个CLI已实现，但现有4f代码仍采用旧统一source审计，不能作为两域合同运行。008先交修改后的可验证CLI、身份版本与候选命令；验收部署后Codex补齐最终SHA与机器路径。不得给“运行eval”或只有占位符的伪完整命令，不自动nohup／tmux／scheduler提交。

## 11. 结果解释边界

普通00会停，外部11不会停：完成判断向外部预完成状态迁移存在问题，不直接证明内部推理缺陷。
11／01结束改善但10仍失败：支持全局停止不足以解决剩余任务适应，仍需区分目标选择、状态恢复和底层执行。
若三mask都改善，照实缩小原结论；若原基线本来表现好，也照实报告。
普通停止验证不足时不能声称已排除没学过停止；不得用false-positive head人为压低基线。

当前旧10的60%（3/5）在H内未完成，仅补完成后停车不会替它完成剩余目标。旧数字是历史结果，不是新FINISH协议成绩。

## 12. 文献依据与状态

World-Env／RehearseVLA：LIBERO逐帧完成标签训练独立reward head，有终止机制；公开默认eval仍需区分GT done路径，不当作现成OFT finish token。
https://arxiv.org/html/2509.24948v6
https://github.com/iSEE-Laboratory/RehearseVLA

OFT输入中的EOS是每次动作响应序列边界，不是任务级FINISH：
https://github.com/moojink/openvla-oft/blob/e4287e94541f459edc4feabc4e181f537cd569a8/prismatic/extern/hf/modeling_prismatic.py

本计划修订没有加载VLA/训练或修改benchmark实现；用户已有一次旧38技术错误和一次新版4f单11四步预检通过，不混作模型成绩。Stage03科学审查/UIR仍未闭环，Stage04/007/008不因修订自动closed。

下一步操作：X交付007代码、CPU/fake测试和实际命令；Codex建议式审查、验收后上传与补齐用户runbook；用户启动和监督实验。

## 2026-10-13：实施前审阅澄清（不改变范围）

X的[需求审阅](https://github.com/No1dry/LIBERO-Remain/blob/75a3eeade994912e28f47fe5c1a2b01f034569a0/collaboration/responses/007_scope_review_20261013.md)已获Codex[回复认可](https://github.com/No1dry/LIBERO-Remain/blob/main/collaboration/reviews/007_scope_response_20261013.md)，可按原007进入独立实现，不要求重写计划。

- 阈值搜索有结果、validation证据有效、普通停止能力建立不是同一状态。零提前误停但全部不FINISH时，候选及时率0，不能声明能力已建立；效果不是代码验收门槛。
- 来源隔离仅约束新增finish head训练／校准，不能据此声称冻结SOG10动作网络从未见过这些原LIBERO来源。base与head训练范围分别披露。
- 合规FINISH率不等价于旧UIR，不证明全过程无冗余。无破坏／无禁投且预算内正确结束的重复试探可能成功；本轮只用延迟和行为证据作诊断，不恢复人工UIR主项、加VLM judge或次数硬上限。
- 5条validation／10条normal测试是pilot，零观察误停不等于总体误停为零；shadow后续任务动作不能认证active退出保持。

算法、预算、默认参数、实验上限与用户运行职责保持；这不是代码交付／accepted／阶段closed。下一步由X独立实现，Codex审查部署和命令，用户运行实验。

## 2026-10-14：用户确认与当前下一步

用户通过明确回复批准A：两个来源域、复用已下载数据，且承认物理祖源独立性未证明。本节和两域分组取代历史007 E节／本计划初版的统一source映射先决条件，其他FINISH/训练/metric合同不变。原初版及旧审计/失败证据保留。

当前下一步：X按008实现与CPU/fake交付；Codex审查部署并给真实audit命令；用户启动audit，确认类覆盖/unknown后才进入feature与训练。已经完成的11预检不重复；若008违反范围修改hold才需重新讨论验证，不预先加实验。
