# Codex：009 Round 1——软件验收与纯文件计划已就绪

2026-10-16。裁决：**accepted（软件及文件计划）**，无需本轮返修；009／Stage04未closed。PR #6当前open/unmerged，Codex不自动合并；本轮没有native诊断、VLA/head/processor或训练执行。

[X交付](https://github.com/No1dry/LIBERO-Remain/blob/2c6dc4c20a12b4b894a3919d79b9bf810648332d/collaboration/responses/009_round1.md)：已测实现5410355436ef0f418f0c95c47293efbdce905b07，最终2c6dc4c20a12b4b894a3919d79b9bf810648332d，二者仅回复/STATUS差异。已确认PR #5合并main3d361f44a9393638d41738d375004e8ea7794301的原生产实现与实际3433f48一致；未以代码合并冒充科研closed。

## 审查和测试

新增生产仅release_audit.py／release_audit_plan.py／release_audit_native.py，原environment／runner／release／calibration／训练／adapter／指标逐字节不改。plan绑定原run/raw/bank/已settle state/XML/BDDL及完整原ledger；run建env前重验1072源文件、计划和float64动作。292边界、旧truth/clearance／原query观察hash、首差异停、partial／清理与typed NPZ合同已核。无研究model/head/processor调用路径；不把原未校准状态当诊断前置成功门槛。

原生侧只读状态API、robosuite底层对象、固定2.3.7 mask4095／geom/contact字段、依赖源码路径与hook清理已独立核；不引入新距离／release标签。原初始化必要调用允许，recorder阶段只允许state读；记录Python入口计数而非宣称覆盖C内部调用。前后指纹证明范围、旧隐状态不可完全复原的限制准确保留。

- Codex本地全套：1988 passed／12 skipped，78.62秒。11可选固定sim源码未装、1 imageio_ffmpeg未装；JUnit SHA62ae0b57ccd47f89ee2c0c4fbb37d89983acf14aaa8dbf661123c143f71b4663。
- 服务器新诊断155 passed／0skip，39.00秒；JUnit SHAf82ad562b13fd3b93df30f2f5007a84e9eb2325517d9fe4eeb3d5983d84779cb。
- 两路独立CPU/fake复核分别92与63 passed，无明确阻塞；均未运行真实native、研究头或VLA。
- X所报1985/15与本地1988/12是环境skip差异，不重复累加成一套成绩；不拿fake通过当物理认证。

## 已部署与纯文件plan

新源码/HUBU-AI096/zp/ICML/LIBERO-Remain-stage04-release-2c6dc4c；新根/HUBU-AI096/zp/ICML/stage04_release_audit_2c6dc4c。293个Git blob和SHA256、4冻结部署文件均本地／服务器核验；原venv／依赖／LIBERO资产复用，不升级。原XML dad2437d…的89引用／87唯一资产通过新解析器纯文件核对，未native加载。

Codex已执行唯一纯文件01_plan，status=plan_ready、exit0/tee0；冻结292×7 float64原动作逐bit一致、293最大快照、37个原query对照0..288、1072源文件。plan内部SHA8bfc498562ef72c0432fa39aed0055ef1328e388f88af08cc27cddeaaec2ea3d；文件SHAa99b5630c7f76a6860719600ff0f4326d7960ca1fe551df27ecc5fc173f626a4。动作数组SHA33dee7b84fa13cdf374aaacfbd4298ef884936eae9ef9848ee6d2ff0844256b7。构建保存state文件SHA和数组bytes SHA、initial artifact摘要和原raw query摘要是不同口径，均按原接口重算，未混用。

[完整服务器命令](../../docs/experiment_plans/stage04_task009_server_runbook_2026-10-16.md)。用户现在只启动release_diag 02_run run；run目录／02日志此前不存在。不是又跑VLA，也不是正式停止/Remain实验。若mismatch或技术问题，保留首差异和partial，不原地重跑、改容差或直接叫模型失败。

[验收长期记录](../../docs/stage_summaries/stage04_task009_software_acceptance_2026-10-16.md)／[机器证据](../../docs/stage_summaries/evidence/stage04_task009_acceptance_2026-10-16.json)。原calibrated=false／threshold=null与所有历史raw／partial／脏工作区保持；本次无代码实现推送、PR自动合并或删除，精确待删=[]。
