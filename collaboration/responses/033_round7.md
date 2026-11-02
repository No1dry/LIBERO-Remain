# 033 R7｜版本化A杯子位姿稳定准入交付

日期：2026-11-02；身份：X。已fetch最新main `28aed1dd5fecd4beeef7dcbea8d1e9c00b7b0bec`，完整阅读R7工单/审查与R5记录分析，合入基线 `9f70255`。STATUS合并仅保留两侧历史条目，未覆盖R5/R6结论。本轮实现commit：`c8c50e639b01802382b2bdfee73f0f946e8c465a`；沿用 [PR #14](https://github.com/No1dry/LIBERO-Remain/pull/14)，不自动merge。

## 已完成及当前真实状态

已按用户明确确认的R7方案实现独立物理profile、构造/回放/reader接线及窄入口，复用R5几何和全部20个原通过来源。95项新增CPU/fake最终通过，受影响旧路径回归通过，独立审阅无未关闭阻断。未运行真实仿真、制备、回放实验、模型或训练，没有修改冻结部署。

真实状态仍按原R5报告为**20 ready、1 failed、9 not_attempted**，微波炉首0未通过。R5软件验收保持；本轮不称10个来源已物理修好，也不把原9600条settle采样或末150采样点补成新证书。那些末150点只有149个控制间隔，且缺完整state/contact，不能替代正式150控制步/151观测与独立回放。

## 显式新规则

- `stability_profile=active-free-object-pose-stability-v7`，独立于不变的 `observation_profile=named-uint8-rgb-one-level-v6`。
- 只允许nine-mask10/mug_microwave_close、A杯white_yellow_mug_1、官方index0..9，使用原R5 method。非法组合在新目录/native backend之前拒绝。
- 150控制步/151观测中，A位置全窗bbox对角跨度≤5mm；归一化四元数的最大两两最短旋转≤1°，通过abs(dot)使q与−q等价，零/非法四元数拒绝。不是只比较各帧与初帧而漏掉两侧相反漂移。
- A全部qvel原样保留，记录每观测最大分量超过0.01的比例及峰值，仅作为诊断；不清零、裁剪、替换或锁定，不改变它在后续真实物理中的作用。广义速度保留各关节原生单位，不统一称m/s或rad/s。
- 所有非A qvel继续0.01；全场景位置、机器人/reference、穿透≤2mm、native10/Open/保持谓词、原RGB/非RGB/状态/hash检查保持。仍为150构造和分别恢复的150+150回放。
- 前置20观测同样用A位姿窗口、非A速度和其他检查；不增加24候选、base80、min80/max400 HOLD。不改 `microwave_candidates.py` 或通用几何，不新增姿态/等待预算。

这是由来源准备现象触发、用户批准的**事后测量假设修订**，需要在新增30条模型评测前披露并冻结本版本；没有利用VLA成功/失败挑来源或更换index。未声称已经精确证明求解器/接触成因，也不将位姿稳定定义等同于可达性或可执行性证明。

## 实现与完整证据

`stability.py`提供纯数组计算和实际编译joint绑定。绑定包含全部joint的类型、qpos/dof起点与维度、完整state layout、唯一A free joint及模型XML hash，检查完整分区无遗漏/重叠；不使用魔法索引。raw qvel必须与raw state对应切片逐位一致，A monitored position必须对应其raw pose。

构造和每次正式恢复都从实际model重新核对绑定。manifest、episode、construction report、audit和replay report显式携带同一profile/binding；snapshot中的实测绑定必须一致。每个新settle样本及正式窗口保留完整state/qvel、A pose、原谓词、接触深度与观察检查，不用bool代替缺失证据。

正式audit使用 `remaining-goals-validation-v2-active-pose`；前置settle使用独立 `remaining-selected-component-settle-v3-active-pose`，明确velocity limit只用于非A。static0只可允许进入完整构造150，其technical acceptance始终false；不足151点、缺第二回放或失败前缀不能成为ready。

reader重算全部raw151点、位置/姿态/速度与缓存诊断、原物理/观察检查及独立回放身份。未知/缺失/错配profile、state/pose/qvel不符、映射变化、姿态/位置超限、非A速度/谓词/穿透/机器人/观察失败均拒绝。旧RGB证书不能授权R7，也不能对R7做RGB-only离线派生。

旧v4/v6解释及旧证书保留；新schema不让冻结06817e61 reader把R7误读成旧v6，低A速度也不能通过改名降级。**R7工件须由新隔离checkout reader处理**，不要求、不修改冻结旧reader目录。新reader同时支持旧20各自原profile，因此旧20不用重新测量，也不冒称它们已有新姿态认证。

## 原20复用与首源队列

新增 `repair033_pose_stability prepare`，仅约75行窄接线，复用R5顺序队列和selected_preparation操作账本，不建立第二个执行框架。选择继续使用R3固定report/sources中20个ready引用，额外强绑定R5实际失败报告作为修订前证据：

- R3 report SHA：`195c8a38c8bb8f4683cf0a4d3925348b5f08e64941621b3379a0ffec57a61f04`。
- R3 sources SHA：`3454ee8a1a776f357a05511c98e12bd9e8c63aba548a0db9f6eb8a32aec6369e`。
- R5失败报告 SHA：`d0ca805413e78cd9fbfee212b1d8b66f93d802f90969f37ad3b0dbd9193b4fcb`，固定20ready/1failed/9not_attempted。

入口将用文件reader复验原20、证书和引用一致性；缺失只阻断，不改为重建。新输出保存三个原输入的逐字节副本，组合sources保留90条expected及旧六/旧20引用。没有重新做30来源plan，没有改原失败或raw。本轮未读取服务器全部原工件，不能把fake入口测试表述为服务器文件复验已经执行。

0号是本批第一条：只有完整新构造+两次独立回放被reader认可为ready，才派发1..9。失败时其余9保持not_attempted，缺子证据保持interrupted/unknown。continue绑定原输入/修订证据/profile，不重试已尝试失败或running；构造完成但回放未尝试时沿用原worker只补回放。新输出不得与原证据重叠，不在旧R5输出retry。

## 必要CPU/fake验证

Python 3.12.7。以下在独立工作树执行；native边界使用明确double，其余producer、审计、文件写读、正式ReplayAuditEnv和归档验证运行真实软件路径。未跑全库或历史53/234/280大组，也未重跑R5几何测试。

```powershell
& 'C:/ProgramData/anaconda3/python.exe' -m pytest tests/test_task033_r7_stability.py tests/test_task033_r7_producer.py tests/test_task033_r7_reader.py tests/test_task033_r7_queue.py -q --tb=short --basetemp=.work/r7-final-profile
# 95 passed in 17.10s：核心28、producer20、reader38、queue9

& 'C:/ProgramData/anaconda3/python.exe' -m pytest tests/test_task033_r7_stability.py tests/test_remaining_validation.py -q --basetemp=.work/r7-stability-final
# 99 passed in 2.02s：新28 + 受影响旧validation71

& 'C:/ProgramData/anaconda3/python.exe' -m pytest tests/test_task033_r7_producer.py tests/test_task033_r5_builder.py tests/test_task033_r2_settle.py tests/test_selected_producers.py tests/test_remaining_replay_candidates.py -q --basetemp=.work/r7-producer-green-dynamic-tolerance
# 70 passed in 10.84s：新20 + 受影响旧producer/replay50

& 'C:/ProgramData/anaconda3/python.exe' -m pytest tests/test_task033_r3_evidence.py tests/test_task033_r3_review.py -q --basetemp=.work/r7-reader-legacy
# 24 passed in 15.43s：旧v4/v6证书/失败解释兼容

& 'C:/ProgramData/anaconda3/python.exe' -m pytest tests/test_task033_r7_queue.py tests/test_task033_r5_queue.py -q --tb=short --basetemp=.work/r7-queue-green1
# 17 passed in 2.45s：新9 + 受影响R5队列8

& 'C:/ProgramData/anaconda3/python.exe' -m benchmark.remaining_goals.headless.repair033_pose_stability --help
& 'C:/ProgramData/anaconda3/python.exe' -m benchmark.remaining_goals.headless.repair033_pose_stability prepare --help
git diff --check
# CLI help和diff check均exit0
```

新增95项与上述组件执行有重叠，不重复累计；另有153项受影响旧用例（71+50+24+8）通过。端到端fake验证80 base+80 settle+150构造+300回放=610次Python double控制调用、三份独立151点正式证据、A非零原qvel/quat保留及reader/archive/snapshot完整往返；610不是新真实控制样本。

RED阶段分别观察到缺失profile/API/helper/入口的预期失败再实现。联调修复了R7正式reset第5个compiled-binding检查字段以及旧调用不应收到新增None参数的问题。根最终复核又发现动态settle误用初态非RGB完全相等、以及numeric equality漏过signed-zero刷新：先补5e-9/2e-8/signed-zero测试，看到2fail/1pass后修正。最终动态恢复原1e-8，非步进state按float64位模式精确，初始/reset原规则未变。最终95聚合在这次修正后执行。

独立审阅完成代码/接口/证据核对，4个定点CPU fake通过（与95重叠）。其首次默认tmpdir权限导致两项setup error，切换新的`.work` basetemp后仅重跑两项并通过；不是产品失败。窄修复另经只读delta复核，无未关闭代码问题。

## 交付与待用户完成项

[完整R7运行手册](../../docs/task033_r7_pose_stability_runbook.md)包含固定commit的新clone、原仿真venv、三个输入、新输出、首次执行、continue、日志/退出码和只读进度命令；不会串联模型。建议新代码目录 `/HUBU-AI096/zp/ICML/LIBERO-Remain-task033-r7-c8c50e63`，输出根 `/HUBU-AI096/zp/ICML/task033_r7_c8c50e63`。部署/真实命令本轮均未执行。

下一步Codex审查并隔离部署，由用户启动必要新构造及独立回放。若0仍失败，保留完整证据后交回裁决，不盲跑9条、不自动改更多阈值。等全部30新来源齐备，再一次评新增30条10；模型仍原OpenVLA-OFT SOG10，输入/计分/正式90分母不变，旧六60条10、00九任务90、原20全部复用。无部分20、allow-missing、FINISH/selector、训练、自动merge或历史清理；033整体仍open。
