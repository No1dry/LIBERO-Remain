# Stage04：009真实诊断完成、包络保守性证据与版本修订授权

2026-10-16。[009 R2](../../collaboration/reviews/009_round2.md)接受用户真实run，最小诊断任务范围完成/closed；不是原VLA停止能力或主benchmark成功。Stage04仍开放，旧校准未建立不变。

## 完成与取证

冻结2c6dc4c20a12b4b894a3919d79b9bf810648332d；用户仅执行init35原已settle初态的step1..292。292/292控制动作（100%），293旧truth对照、37/37原观测hash（100%）全匹配，无mismatch/错误；NN三项0、没有hold/第293步/其他source。静态+293帧294份只读证明一致，7300 native mj_step子步推进14.6秒，初始化与read-only state API另计，hooks恢复。

全部882个manifest条目+manifest自身=883文件，57,650,960 bytes已下载本地reports/stage04_task009_result_2026-10-16/evidence/run；全部SHA/dtype/shape/typed内容验证。压缩包SHA379a73eaf41588a1d5832002ddcfdd9feff640ab884b69f2c107afc995b53708，manifest SHAe62227052379ecb4196cd61b096f268c217fb52dc80dde63b4eb0b97dfe0c75a，summary SHA88c334b81a57e6151a667d533e4c67f26bee66dc14e34d1a38e4649343cdc3cd，log SHA23646fe080c781ed653455cb6e23c727837af79f377450fd87fc9d4914df2e92。原run树和source-plan/动作、static几何与native帧原样保留；旧5条shadow的输入/视频仍留服务器。

[机器证据](evidence/stage04_task009_result_2026-10-16.json)及本地verify_completed_diagnostic.py/analyze_step280_separation.py可复核全部工件与本次纯NumPy几何推导。Codex和两位独立复核者没有运行新native或NN。

## 核心定位

第280步旧球界把番茄box110与掌部mesh74判包络重叠（-23.43mm）；掌部球半径119.06mm，不能代表真实mesh在该方向的范围。全部番茄collision集合最高world-z0.6059793996m，全部hand集合最低0.6207082403m，**分离保守下界≥14.72mm**；汤罐≥90.69mm。pinch净间隙仍+14.68mm，目标-hand contact0，相关mask均兼容、margin/gap0。

原旧规则按设计返回None，不是实现计算错误；本帧证据说明判据过于不充分、不是物体仍被夹住的证明。几何投影符合固定[MuJoCo2.3.7 collision支持表示](https://github.com/google-deepmind/mujoco/blob/2.3.7/src/engine/engine_collision_convex.c)，但不是任意geom精确最短距离，不将本例泛化全部unknown。旧label/calibration与主分数不改；009没测counterfactual FINISH后的W150，也不证明历史全部隐态相同。

这是停止控制的测量修订依据，**不能把measurement unknown当“VLA不懂剩余任务”的主假设证据**。研究方向仍是外部预完成后重定剩余目标和保留成果，finish head只是消除停止接口干扰，不人为压低原基线。

## 用户确认的下一阶段

用户明确同意“版本化修订”：X实现更紧的保守几何分离补充和决策相关鲁棒校准；旧版和旧5条未建立报告保留，模型/head/训练不改；**追加5条新版official-init35..39 shadow由用户启动，累计模型预算30→35**（5旧+5新+10独立normal+15Remain，最坏23450物理步；audit/features/parity/292诊断另计）。原30预算文档保留历史，Plan4末节增补覆盖本次新阶段，不偷换预算。

[任务010](../../collaboration/tasks/010_versioned_release_and_calibration.md)已给X，明确：
1. v1 True/False及接触/pinch安全边界保留；只对无contact且pinch>2mm的近手unknown补box/compiled-mesh在world x/y/z轴的整个集合分离证书，不加距离API或改碰撞/阈值。
2. 完整身份/证据仍必验；first-hit False/None不能放行。tau双端只作不确定区间，及时性必须稳健、timing_unknown候选不能选；无关后续unknown作覆盖诊断，不自动整条否定。
3. 显式版本贯通全部读写/active绑定；旧头v1训练事实、原hash/raw默认行为不变。新5条一次真实采集保留v1/v2事实，派生2×2对照；正式新校准仅新规则+新测量，敏感性输出不作为主阈值。
4. 主metric仍少量；证书是取证，非新增一堆benchmark score。独立10条normal_test40..49与Remain从未用于挑规则/阈值；披露修订在旧pilot之后提出，不把校准开发伪装独立泛化。

X写代码/CPU-fake/PR；Codex审查部署后给新5条命令，用户启动。现在用户不用重跑009或原shadow，不直接active。当前旧calibrated=false/threshold=null，stop-capable尚未建立。009完成与010 open分别记录，PR #6由X按accepted合并保留最新文档，Codex不代merge；未合并交流仍保留。原始数据/脏工作区不改，无删除，精确待删=[]。
