# 给X：008 两来源域的FINISH数据审计与身份接口

日期：2026-10-14。状态：**open，新需求，用户已明确批准A**。这不是007返修；007/4f76f49软件已accepted且用户同一source0_11四步真实预检通过。X改代码、做静态/CPU-fake与GitHub交付；Codex文件准备、审查部署、给完整命令；所有真实仿真／标签／VLA／训练／eval由用户启动。

研究规格：[修订Plan4](../../docs/experiment_plans/stage04_finish_protocol.md)与[用户批准的两域设计](../../docs/experiment_plans/stage04_data_domains_proposal_2026-10-14.md)。字段／代码布局可合理设计，但以下行为、边界和身份消费者必须一次性落实。

## A. 基准与不变项

1. 先按既有accepted授权合并保持已审实现的PR #4，登记merge SHA；再fetch最新main，从含4f76f49及本任务/Plan4/当前协作规则的main开独立008分支／PR。不把新设计追加成007返修、不暗中漏掉已修OnTheGroundPanda或其他已验收实现。Codex不代合并代码。
2. 只basket、原SOG10 OFT和原finish head。**只改数据来源域／分组／审计／artifact与消费者绑定、配置和文档**。不改hold/release、两类robot许可、H520/W150/chunk8、policy seed7、camera/crop、原指令、动作解码、模型权重、优化器/MLP、阈值规则、metric或旧raw。无GT router、VLM judge、记忆／remaining提示，不卡初帧可见性。
3. 不新增VLA数据采集rollout。复用已核官方HDF，真实audit只为预定head_train/validation采样恢复与K4标签；head_unused只做必要纯文件检查，不为了补覆盖恢复/采集评测来源。模型eval仍5+10+15=30条、最坏20100物理步；parity64forward、特征和标签物理费用另计且由用户启动。
4. 来源独立性主张收窄：保证明确轨迹级分组、不直接训练编辑评测输入；**HDF与eval init物理祖源独立性未证明**。不得因namespace不同就置independence=true，也不能声称冻结SOG10未见eval来源。真实head效果差不是代码返修条件。

## B. 明确的两个域与固定组

| 域 | 源材料／键 | 固定角色 |
|---|---|---|
| head示范轨迹域 | 实际HDF字节SHA＋实际group名trajectory_id；例如hdf:{sha}:demo_35 | train demo_5..34，30条；head_validation demo_35..39，5条；unused demo_0..4、demo_40..49，15条 |
| official eval初态域 | 实际init文件SHA＋官方initial_state_index；例如init:{sha}:35 | normal_calibration init35..39；normal_test init40..49；Remain init0..4及全部编辑变体 |

group名字中的数字只选择文件中现有轨迹，不是采集seed／eval编号。`demo_35`与`init35`没有映射声明。HDF unused不叫“eval test来源”，不能用unused demo_0..4说明Remain物理来源留出已经证明。

配置和artifact必须可区分**head_validation**（val BCE／parity输入）与**normal_calibration**（5条普通00 shadow校准阈值）。不要把一个歧义`validation/source_index`同时当两个域，也不通过名字strip数字恢复假对应。可保留整数作展示，但分组／绑定按具名domain与实际键。

组数量与成员固定，不按标签或表现挑容易样本。缺group／非法key／重叠组／实际文件hash变化／类别不足等明确insufficient/error。若将来改组需要新用户确认记录，本任务不自动替代分组。

已核材料：HDF revision147fa5eb607bb696dd922c3518084a90954cd2f3、SHA3173ebc709b064683956b757ae8737909457d730aa305b23c5735292e59066af，50轨迹／14700个123维states／50actual XML。init SHA1899fe54c51e24a41d5f9e32254730d6777f4894ab68e0e873f1fa7ae2062030、50向量；BDDL SHA2e661058917f683a25bce480015197f0a2c1911bcbc2b9dd9d947199069c9618。实际SHA从文件计算，不只信config自称。

服务器HDF：`/HUBU-AI096/zp/ICML/stage04_finish_38e6a44/assets/libero_10/LIVING_ROOM_SCENE2_put_both_the_alphabet_soup_and_the_tomato_sauce_in_the_basket_demo.hdf5`。固定LIBERO/init/BDDL与sim、model venv仍旧stage02 .runtime，源包仍source001/replay。Codex部署时填最终新路径，不在GitHub放密码、权重或大数据。

## C. 数据计划／注册／真实audit

1. 新data config/profile声明两个域、全部成员和角色、原HDF／init／BDDL、原指令、stride8等；纯plan显示实际文件存在性、域／组、运行边界。可以复用现有入口；不要求新命令名。帮助、默认CPU/CI、plan不能创建环境、加载VLA、生成标签。
2. HDF registry读取实际trajectory states与model XML，记录group、采样frame、数据hash、state/observation身份。**不再强求HDF首state与official init相等，或所有50个eval source都有对应演示**；不伪造旧collection_provenance/manually_confirmed，不把demo group用于official source_index。
3. official init registry用安全CPU loader核原文件hash／向量数量、请求index确实存在，记录eval组及实际官方源state摘要。Remain/normal来源继续验证真实episode.initial_state_index、saved state/modelXML/BDDL、source/replay/preparation绑定，旧0..4及新35..49对象不变。不为注册eval身份启动仿真或渲染全部test。
4. 真实audit由用户命令启动；只恢复采样head_train/head_validation（stride8＋最后state，按已声明规则），使用实际XML与layout、固定BDDL原任务，保存**当前合法观测**，再取当前GT/释放与必要K4独立保持。不能先做label分支再把未来图当输入，结束恢复原状态，源HDF全字节不改。
5. 原label contract保持：当前目标未全满足或已证明夹持为0；当前全满且released=True、同状态K4 passive hold稳定为1；缺释放/几何/保持证据为unknown，不偷造负或正，不用末帧/is_last/未来任务动作/时间当标签。成功示范缺失败/停滞负例继续披露，不自动采补。
6. 轨迹在train/validation/unused互斥；保留跨head组直接重复state检查、已审计raw observation重复/身份验证。能纯文件核的不用新增render；这些检查不证明跨域物理祖源独立。拒绝将已编辑评测样本／eval state bank／normal校准/测试输出直接放入head缓存或训练。profile、domain、label、来源key、frame index/time、GT仅metadata，policy/head合法输入白名单不变。
7. ready_for_feature_export仍要真实物理audit完成、已知train/validation各有0和1、无关键issues且身份完整；file-only registry不能标ready。输出按域分别source/group coverage、0/1/unknown、物理恢复/hold计数与原因。保留new-out/no-overwrite、partial/close/error语义；不自动跳到feature/训练。

## D. 身份版本与全部消费者（不能只让audit过）

可用新schema版本或明确必需的data-profile版本区分，具体字段名由X选；要求语义一致、hash可审计，**新两域路径不能默默接受旧统一source合同或把旧整数当新键**。旧读／旧默认／历史scores保留，旧结果不覆盖；若仍支持legacy运行须明确选择，不能与新profile混用。

至少盘点并更新：data registry/audit和validate_audit、feature cache及load/export、head保存/加载identity、training、data_commands选择parity输入、workflow dry-plan/run/normal-bank绑定、calibration expected组和阈值artifact绑定、example config与runbook。控制协议/episode评分不要求为数据分组改算法。

- audit→cache→head继承同一HDF/head分组身份与eval registry/profile约定、原物理label contract、base/code/input/feature hashes；已改文件hash或域/组失配拒绝，不盲信label列。仍复算物理证据label。
- train仅head_train；pos_weight仅其已知0/1；checkpoint仅head_validation普通BCE，earliest tie；不接受unused/eval/校准轨迹，不借它们补类别。
- **32不同输入parity来自HDF head_validation**，实际state/raw observation/model输入去重，不用normal_calibration、normal_test、Remain或train凑32。仍同worker恢复Python/NumPy/Torch/CUDA RNG、每输入原/只读shadow两次forward、预先声明容差、头/原动作一致性，不新建仿真。
- **阈值normal_calibration来自official init35..39**，不取head_validation group数字、train或test替代。5条shadow的first-hit、固定分母、零及时率不能假通过、head/base/schema绑定不改；calibration记录清楚eval域／role／source成员/profile／head身份。
- normal_active只init40..49，Remain主只init0..4×10/01/11，source001/replay不变；job用eval registry分组，核本head与本calibration相容，不要求head HDF trajectory键等于eval init键，也不完全删除组校验。shadow新主项N/A保持。
- 新head/dataset/profile/threshold/source registry被替换、域换名、文件同名不同SHA、head/calibration/eval组失配、旧artifact混入新profile都明确拒绝。metadata新增字段不进网络、不触发额外predict/reset/step。
- runtime crop/seed/chunk冻结和base参数身份仍按已验收机制，Codex部署继续冻结同一runtime文件；本任务不另加换输入/模型方便功能。

## E. CPU/fake测试一次交齐

使用tiny合成HDF/受控provider/model worker，不启动真实LIBERO/模型/训练。至少覆盖：

1. demo与init首state全不匹配，但两域文件／组有效时可进入**fake**物理audit；不制造demo→init映射或manual confirmation。file-only依然未生成标签/ready。
2. 相同数值后缀的两个域不是同一键，head_validation／normal_calibration各自取正确数据；artifact明确物理祖源unproven。错误域/角色、成员重叠、缺group/index、实际hash更换拒绝。
3. 跨head组同轨迹/直接重复state与观测、编辑test/eval行进入head缓存、未知label被篡改、末帧假label、非法metadata进model输入都拒绝；0/1类别不足不训练。
4. audit/cache/head/job/calibration/parity各消费者新profile一致；旧统一source artifact不能混进新两域job，旧默认/历史raw/score读取不改。
5. epoch选择用head_validation；threshold用normal_calibration；unused/normal_test/Remain不能参与任何拟合或选择。32不同输入只来自head_validation，不足报告不足、不借test。
6. 5/10/15固定eval集合、H/W/chunk、GT不控制Stop、first-hit、零FINISH不建立能力、暂停/partial/no-overwrite与资源关闭原回归仍通过。
7. OnTheGroundPanda修复及安全合同回归保留，真实四步通过记录不改写；数据域改动没有改hold/release／base动作。已有冻结／同forward／RNG／label被动分支测试保留。

复跑相关FINISH文件＋全套纯CPU tests，报告passed/skipped与原因；不能把fake audit或synthetic head训练叫真实科研成绩。不要求X用GPU测效果来交软件。

## F. 配置、CLI、交付和审查

保留独立显式阶段入口，提供真实实现支持的全部参数。例配置准确列两个domain/profile、30/5/15 HDF组及5/10/5 eval组，并说明两个validation角色；不要留下能误用旧trajectory_source_map的默认模板。

候选runbook应逐阶段写：纯文件计划／预算与registry；用户真实audit；feature；CPU head train；normal-bank准备／32输入parity；5 init normal_calibration shadow／freeze；10 normal active；15 Remain active；可选shadow／K重评分。写python/cwd/输入/新out/log/status检查，不自动串联、nohup/tmux、安装后运行、重新下载HDF或新增采集。实际机器绝对路径和冻结SHA由Codex部署后最终补齐。

交独立PR与`collaboration/responses/008_round1.md`：base/实现/最终SHA、精确改动、语义版本及消费者盘点、全部CPU结果、help/纯计划参数核查、未做真实阶段、限制、实际候选命令。X不自行accepted/closed，需求之外合理实现可说明，不因风格/效果返修。

只有明确泄漏、错域/标签/身份、关键消费者未迁移、危险控制、假成功或核心命令不能运行才阻塞。用户A已批准，但本任务不是批准X/Codex启动实验；Codex验收部署后用户先运行真实audit，数据充分才到feature/训练。007/008及研究阶段都不自动closed，交流、旧失败与成功报告全保留。

下一步操作：X先处理已accepted PR #4合并登记，再独立实现008与CPU/fake交付；Codex审查部署；用户启动真实audit。代码执行者：X，实验启动者：用户。
