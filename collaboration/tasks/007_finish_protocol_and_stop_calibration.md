# 给X：007 统一FINISH协议与停止校准基线

日期：2026-10-12。状态：open。阶段：Stage04／Plan4。  
用户负责所有真实实验的启动、运行、监督；X负责实现／CPU-fake测试／GitHub交付；Codex详细需求、建议式审查、验收后上传服务器和完整命令，不代跑实验。  
研究规格：[Plan4](../../docs/experiment_plans/stage04_finish_protocol.md)。下述为必须落实的功能，不是要求特定代码布局。

## A. 基准与交付边界

1. 先按既有accepted授权处理PR #3合并／登记，从包含04508dc已审实现与最新协作规则的main开独立007分支；不要继续把007放入PR #3。不暗中合并其他未审代码，交付写base／实现SHA。 文档冲突保留2026-10-12新规则／STATUS和007／Plan4；仅文档解决不反复重审未变的实现。
2. 本次只basket＋现有SOG10 OFT＋小finish head。旧默认all／pilot、raw、JSR/UIR语义及旧结果保持；不补VLM judge，不训练动作策略，不扩任务。
3. X可运行静态与CPU/fake单测；真实MuJoCo运行、数据恢复、特征抽取、真实VLA前向、训练、校准和eval均给用户命令，不自行执行。无需为真实资产缺失伪造通过结果。
4. 关键需求不清先在本任务首轮回应中集中提出工程选择／缺资产；无需等待Codex对命名／模块位置等细节逐项许可。合理等价实现可直接提交并说明。

## B. 独立finish-v1运行与证据

推荐新CLI/runner/metrics/evidence模块，或清晰版本分派；旧入口保持。

- H520对00／10／01／11一致，chunk8；允许t0；只在队列耗尽query；H最终query时active有效FINISH优先，否则TIMEOUT，不能执行H之后的模型动作。
- active应用head FINISH；shadow只记录head FINISH，继续原动作到H。head_decision与applied_decision分别存，不能把shadow头预测当真实退出。
- 接口可用带版本的dict或等价类型：候选动作8×7、logit／p、threshold、head_decision。候选动作和实际执行必须分开；FINISH不执行该query候选动作，记录accepted/executed=0。
- 无GT门控：模型错误FINISH也必须退出并评分失败，不替它改成continue。mask、goal truth、step/H、episode/source id与label不进head，不改原指令／crop。
- FINISH和TIMEOUT均safe hold W150真实物理步；不再predict、不冻结sim、不由env.done停止保持。hold只依据允许的proprio／控制状态，不根据目标真值做释放／修复。
- finish_step=f或null；timeout_step=H或null；exit_reason明确；实际trace为0..f+W或0..H+W，全部control step连续。政策超时与运行技术timeout分开。
- 原pilot_evidence要求hold挂在STOP query，不能原样复用并把预算timeout伪装STOP；提供新版本ledger。每hold记录cause=finish/timeout。
- 每query保留观测步、实际预处理输入hash和两路裁剪图引用、候选／接受／执行动作映射、head版本／logit／p／阈值／两种decision。输入证据不得额外改变policy calls、RNG或环境step。
- head缺失／bad artifact、非法概率、版本不符、无hold contract、录像或关键证据失败：显式技术暂停，保留partial、expected和后续missing并释放资源。已完整执行但政策失败继续，不挑新来源。
- 新输出拒绝覆盖；read/rescore识别协议版本，不能混读为旧JSR。评分由原trace／ledger复算，不信缓存标签。

## C. 自动任务契约

主项：合规FINISH成功率，百分比＋n/N。原无FINISH模型不适用新主分数；shadow为诊断，主字段不假装active失败率。

active成功需f<=H、在决策状态已全目标满足并释放目标对象、初始成果在0..f+W保持、全目标在f..f+W稳定、全窗口无禁止投放。不能靠hold之后出现成功救提前FINISH。

禁止投放：初始篮外的非目标可移动对象，新增入篮且释放后稳定保持；排除篮子／桌子角色、初始篮内额外对象、瞬时经过和纯接触。默认确认4控制步，显式config/version；提供1／4／8敏感性重评分。确认事件粘滞，后来恢复不能擦除。

释放检测要用真实夹持／接触与必要几何信息，记录具体方法。模糊或缺失不默认为released=true，不从动作命令直接猜。X可选择可靠的实现方式，说明算法、适用范围及CPU测试；真实正确性预检由用户运行。

失败原因自动分开：premature_finish、no_finish_timeout、unfinished_goal、goal_regression、forbidden_placement、unstable_after_exit；技术错误／unknown另报。可多原因，不强行互斥。

诊断结束延迟：τ为首个已全满足且释放的稳定区间起点，f−τ；有效11 τ0。确认使用未来帧只作离线参考；不进策略。timeout／提前FINISH／无τ单列并披露覆盖，不静默删除成低平均。详细约定见Plan4。

## D. OFT只读特征与head

1. 捕获原L1实际使用的(B,56,D) action-token hidden，不改变输入token／attention／dtype／crop／proprio／原forward；沿56个位置均值pool。不含EOS、prompt、patch，不把EOS预测当finish监督。
2. 复用一次forward中的原候选动作，不能为head另预测一次、改变query频率或增加记忆。shadow分支始终原动作；active只有退出差异。
3. 原backbone、LoRA、action head和projectors全部eval／requires_grad=false；特征detach。只优化head；训练前后原参数hash／梯度状态可验证。
4. 默认LayerNorm(D)→Linear128→GELU→Linear1，无dropout；head FP32，接口feature dtype转换显式；仅在head分支转换，不能改变原动作张量。
5. 默认seed7、AdamW、lr1e-3、wd1e-4、batch128、最多50epoch；普通validation BCE最低选checkpoint，同分较早。允许用户显式改配置并记录，不自动扫参。 head优化采用BCEWithLogitsLoss，pos_weight=N_training_negative/N_training_positive，仅training计数；任一类缺失先报数据不足，不用validation/test补权重。
6. artifact保存head state、architecture／feature版本、base checkpoint及代码身份、数据划分／标签合同、epoch／seed／config／hash。推荐safetensors或安全state_dict加载；不自动下载其他VLM或覆盖base权重。
7. 用户真实一致性检查命令：固定32个独立validation输入，比较原动作与shadow新增分支；不只比最终成功。CPU fake要求逐项一致；真实CUDA若有数值非确定性，事先声明容差并记录最大偏差，不能事后放宽救通过。

## E. 数据audit、标签、划分和校准

先提供纯文件／配置dry-plan和独立真实data-audit入口，后者用户执行。

- 读取正常00示范的真实saved states／回放证据和合法观测生成标签；输入、目标真值、释放和稳定分别存。不得以is_last、t/T或固定长度造completion标签。
- 确认稳定的全目标满足且释放为正；自然partial、尚未释放、接近完成但不满足为负。unknown保留原因，不偷当负例或伪造正例。只有成功示范时，披露缺少失败／停滞负例；用户需要时另采训练来源rollout，不自动启动。
- head输入只用同一OFT合法观测／原指令；source、trajectory、step、split、label_reason、hash仅metadata。
- source/trajectory整组划分，edited variants不得跨组。确认映射后建议train5..34、val35..39、独立normal-test40..49、Remain测试0..4及其全部变体。映射／数量不足先audit和提出确定性替代，不补“容易成功”的来源，不把test用于epoch／threshold。
- 导出feature cache绑定原数据／input／label／feature／base artifact hash，验证维度、有限值、类别／来源覆盖和split无泄漏；数据文件不可盲信行标签。
- 标签稳定确认默认从当前saved state按同一退出hold协议被动推进4步；先保存当前观测，确认分支不回写源轨迹／不作为head输入。不能以示范未来任务动作造成的目标撤销来把当前可停止状态标负。用户运行该真实标签审计；复用等价已存被动保持证据可行，无确认记unknown。eval不为此在线增添额外step或GT许可。
- 阈值仅normal-validation：建议用户5条shadow，候选0.05..0.95 step0.05及0.99；要求观察到提前FINISH=0，最大化τ后24步内正确FINISH比例，同分更高阈值。不能满足则报告能力未建立，不自动用test救阈值。
- 对每个阈值逐episode取真实query顺序的首次p>=threshold作为虚拟退出，按该点当前目标／释放状态判候选正确性；首次提前误停不被后来高分抵消。及时候选比例分母为预定validation episodes，未完成／未触发算未命中，unknown／缺证据单列并停止已校准声明。shadow不是停止后的物理保持实验，最终合规由独立active验证。
- 普通00独立active10条、停止能力报告、真实模型parity及Remain15条都由用户执行。软件正确性和科研head效果分开；效果差不是默认返修理由。

## F. CPU/fake最小测试矩阵

请一次集中覆盖，不需要启动真实资产来冒充测试：

1. 旧默认接口、旧输出／scores无变化；新旧schema混读拒绝。
2. t0 FINISH、H FINISH、H continue→timeout、非整chunk最后截断，FINISH不会凭GT插入chunk。
3. 相同观测／指令改变隐藏GT或mask不改变head输出；GT错误FINISH仍退出。
4. shadow高p不退出、原动作逐项一致；active高p不执行候选动作。
5. NaN／越界p／错head维度／checkpoint不匹配／空continue动作拒绝，无静默fallback。
6. FINISH和timeout均恰好W hold，cause正确；无hold或hold抛错留partial／pause。之后目标漂移不能判成功。
7. finish_step基于决策前动作数，不错移一帧；timeout不伪造FINISH；ledger完整覆盖实际动作。
8. 错对象稳定投放失败；瞬时越区／触碰不误罚；既有额外对象不误罚；取出再恢复不能擦除初始成果破坏。
9. 未支持FINISH模型／shadow不产生虚假的0%主成绩；planned error/missing保持分母与coverage。
10. pooling切片不含EOS等，head训练后原权重／梯度／动作不变。
11. 同源／变体跨split、末帧假标签、非法特征字段、bad hash检测。
12. τ及延迟覆盖处理、未FINISH截尾披露；新旧原始文件全字节不改。
13. dry-plan不初始化仿真／不加载权重／不调用predict；真实命令不被任何默认CPU测试／CI／安装流程自动执行。
14. 所选case技术失败暂停后续／关闭资源，政策失败不暂停／不替换case；观测记录不会增加reset/render/predict/step或变异输入。

## G. 完整运行命令交付

X交付实际CLI，不要求照抄未实现命令名。至少覆盖以下独立阶段：

配置／身份／预算纯dry-plan；真实数据audit与标签；特征导出；head训练；validation shadow与阈值冻结；真实32输入parity；normal00独立active；Remain active／可选shadow；只读rescore／报告与日志检查。

每条命令写实际python、cwd、依赖、全部参数、输入artifact、新输出目录、日志、返回状态和检查步骤。按已知私有runtime提供可配置路径，不在GitHub存凭据。CLI路径尚未落实前，不用假flags宣称可运行。

Codex验收后部署冻结SHA到新服务器目录，再将实际机器路径与SHA填成用户最终runbook。不得自动nohup/tmux调度、串联训练+eval、删除／覆盖旧数据。操作命令须支持用户自己中断并保留证据；能否续跑、重复目录规则明确。

## H. 交付与审查约定

单独PR，collaboration/responses/007_round1.md应含：base／实现／最终SHA，修改文件，CPU/fake真实测试结果／skip原因，全部入口--help与dry-plan，完整候选runbook，artifact与协议版本，已知限制及合理替代设计。没有真实GPU结果就明确没有。

审查仅明确错误或关键合同缺失要求修正：如GT泄漏、错标签／split、wrong deadline、unsafe hold、假成功、证据失配、动作模型被更新或无法运行核心命令。其他建议记为non-blocking，不以偏好反复返修。X不自行accepted，不自动启动实验，不宣称研究结论或阶段closed。

下一步操作：X实现／CPU-fake测试并交PR；Codex审查建议、验收后上传和最终命令；用户启动、运行和监督真实实验。
