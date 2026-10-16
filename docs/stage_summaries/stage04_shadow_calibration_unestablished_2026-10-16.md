# Stage04：5条shadow采集完整，停止校准尚未建立

2026-10-16。**采集作业accepted；停止控制未建立，不是训练命令失败。** 用户运行冻结3433f487d38efe0a08e4c814e87412aad5aba9fe，5/5完成（100%）、330次预测／3350物理step、5视频、errors/missing0、exit0/tee0。Codex只读核验／离线校准，没有运行新模型、头、仿真或训练。

## 本轮结果

既定calibrate完整验证5条raw/inputs/ledger/video/hash后返回capability_not_established，calibrated=false、selected_threshold=null；CLI exit2/tee0是科学校准未建立的既定状态，不是新软件崩溃。官方normal_calibration仅35..39，未使用40..49测试或Remain。原代码／网格／标签与数据不改。

| 0.99网格点的诊断类别 | n/N | 比例 |
|---|---:|---:|
| 首次触发时明确完成且释放，并及时 | 3/5 | 60% |
| 首次触发时释放状态unknown | 1/5 | 20% |
| 未触发，且原任务未全完成 | 1/5 | 20% |

0.99不是正式选定阈值，不能直接给active或宣称模型成功率60%。shadow主FINISH指标N/A，不是0%。3个known及时来自init37（296，tau295）、38（256，tau250）、39（384，tau380）；35在280时p=.990470、两目标入篮但release unknown，292才达到既定known稳定参考；36从未全完成、最大p=.211224，未触发并非head停止失败。当前没有任何同时零premature和零首hit-unknown的网格候选。

## 测量不确定性，不等于模型全失败

校准同时要求整条H+W完成真值无unknown，35／37／38／39四条（80%）不满足。3条首hit正确仍会因早先／后续unknown阻断；尤其37在479..670再次unknown，含整个150步hold。即便只讨论整轨迹门槛，仍有35的首hit unknown，不能简单删门槛救通过。

原始记录283个完成真值unknown帧中281为保守近手/夹持几何包络（99.29%），2为非双垫contact（0.71%），计算异常／字段缺失0。35 step280番茄罐无grasp/contact，但手球包络-23.43mm、夹持包络+14.68mm，AND>2mm规则返回None；不证明真实仍夹持，也不能凭无contact翻True。独立代码与数值复核未发现明确实现错误；原R9软件验收和已完成audit/features/head/parity/bank不撤销。

现有trace/FINISH输入不能重算精确几何或完整native物理状态，不能离线强行重标。两位独立只读复核同意先做release测量审计；不要立刻重训头、重跑全部或直接进入主实验。这是FINISH停止控制的**可测性/有效性问题**，不是Remain“重定剩余任务能力差”的证据。

## 身份与原始证据

- source-run文件SHA0c0fa4803d1e7a8a9b1a3a1ab2fe15f55c7b2e35a66436117d2fddd60283fb9b。
- calibration内部SHAac4cd37c46ae84df2d73bf635998a4faada8dc1dfec3e6f54cb38a018b87043f，文件SHA332d400fc758b5d5f33d4694098a1f9c6cf97f2163c505370400c7bb892336a0。
- head6636f7133943d551df31a14822df440b63c1b98c0b3ee95f4873019492512c7f，run_id65c8ef90d9d7495ebc8234cb814e3b5a；原固定runtime、来源角色不变。
- 原run为/HUBU-AI096/zp/ICML/stage04_finish_3433f48/results/run01/validation_shadow；原calibration为同runroot/results/run01/calibration。read_run已通过全部330真实input及PNG／5视频字节／trace/ledger身份；本地再按同固定calibrate_threshold重算报告完全一致。
- 本地reports/stage04_shadow_review_2026-10-16/evidence保存run.json、summary.json、09日志、5份raw、calibration.json及10日志共10原文件，SHA全与服务器匹配。[机器证据](evidence/stage04_shadow_calibration_diagnosis_2026-10-16.json)含逐文件SHA、每条首hit和unknown区间。**模型输入/PNG/视频原树仍在服务器，未声称全量复制本地。**

## 研究决策与下一步（不启动GPU作业）

[008 R10只读测量审计建议](../../collaboration/reviews/008_round10.md)已给X：核对release包络与两个unknown门槛，提出最小可测性审计／所需evaluator-side证据方案；现阶段不修改代码／指标／阈值，也不伪装成明确bug返修。任何协议版本调整或新增native诊断须先由Codex审查、用户确认。优先复用当前动作/初态/视频，不加载VLA、不用测试组、不重训。

用户暂不用启动normal_active／Remain或重跑本轮；保留原uncalibrated结果。主实验normal_active与Remain均未开始，后续10条／15条预算未消耗；原5条shadow预算已用5/30，不能忽略。当前代码active会拒绝未校准报告，不绕过。

研究目标仍是外部提前完成部分任务后，模型能否重定剩余目标并保留成果；不让保守测量unknown被包装成原模型低成功率。跨域祖源／SOG10 exposure、demo_38两正例等pilot限制仍在。007／008／Stage04未closed；本轮无代码推送或PR自动合并，无删除。总结／R10／证据／STATUS本地和GitHub来源commit+SHA备份，精确待删=[]。
