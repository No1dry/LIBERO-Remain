# 033 Round1 — X 实现与交付

日期：2026-11-02。状态：实现与定向CPU/fake验证完成，交Codex审查和隔离部署；真实来源准备、60条新评测和Eval发布均未执行。

## 版本与范围

- 实现SHA：`1b2ce8b7f88026e6c3aeee1cae22f864e266d183`。
- 独立分支：`x/task033-libero10-nine`，目标main；不自动合并本PR或历史PR。
- 独立PR：[No1dry/LIBERO-Remain #13](https://github.com/No1dry/LIBERO-Remain/pull/13)，已上传代码、回复及命令文档，保持open/unmerged。
- 已先fetch最新main并读取033、Plan6、范围JSON和032。main基点为 `c9145d17a3c279ad7384ad357118095c6b648061`；复用已审031 `ac1301779cf6ae4c34ebc80c20936a4f7a4953be`，同步commit `7059092533b30573c3b219ec6454aa1ff342f580` 只合并最新需求记录，未用main缺失的旧headless假装完整实现。保留013 v2与031 R2保护。因031尚未合入main，本PR包含该已审代码祖先，不意味着要求自动merge PR12。
- 正式task IDs为 **0,1,2,3,4,6,7,8,9**。catalog的官方完整名称、A/B、invariant和Open要求逐项与批准JSON核对一致。
- 00/10各90条；旧六各60条只读复用，总120；新3/8/9各30条，新增模型总60。旧四90不进新默认计划、分母、主表或导出配置。旧两个90未执行补建/补测取消，历史原文件及80/100报告不删、不改；没有宣称物理故障解决。

## 具体实现

1. 新 `nine_catalog.py` 明确active A/B与完整官方谓词映射。3/9的10为物入、门仍Open；Open只用于来源和初态，关闭可完成B。8的两位mask只描述两壶，完整Turnon始终保留，10关炉后恢复也保留sticky invariant违规及明确原因。
2. 扩展原selected-A-only producer、正式adapter回放、源验收和归档。容器按实际运动site位姿放置；双壶保留两壶位置预留；设施与目标角色不误作干扰物。00只原settled base+t0，10沿用150构造和2×150独立回放；没有抬阈值、改index或增加01/11银行。
3. 新显式 `nine-normal00` / `nine-mask10` 协议。00首次完整native成功或H结束；10仍全部官方目标+release连续五观测或H。完整官方事实与native成功互校，模型输入仍原指令/RGB/proprio，新增真值全部留在评价端。
4. `nine_planning.py` / `nine_workflow.py` / `nine_cli.py` 固定new-three执行，只读引用旧六结果。复用缺口永不进队；准备与模型尝试各自持久账本；worker加载之前记attempt意图。中断、已尝试目录丢失、原ready失效均不会隐式重跑或覆盖旧工件。
5. 032离线评分及历史reader保留原model/code/protocol/source/raw/endpoint身份，按每行记录实际读取依赖及证据级别。仅因全局harness变化不拒绝复用；实际模型/统计不一致具体分组、禁止混合聚合，原行不作废。输出与历史根隔离，来源依赖变更单列异常。
6. 新报告固定90每条件，官方00、官方10与合规10分别列n/N和百分比；未开始不是0%失败。00不同端点不池化全轨迹效率。10保留成功条件TCP、等任务宏均值、成功轨迹/计划数及任务覆盖。录像复用原双相机观测帧、原worker和证据链，没有额外物理步。

## 032口径落实

00主分数按可验证的完整官方bool信号曾成功；缺signal、技术错误、缺文件和已执行失败分开。旧合规仅诊断；新00提前终止未采集旧release+五观测端点，旧合规诊断明确N/A，不把首次官方成功冒称旧确认成功。

10只移除已确认 `table_drop` 的合规失败贡献及对应 `event_unknown`。混合wrong-placement未知、release未知、其他确定违规仍保留，确定失败优先。原事件/原分数/新分数/逐条diff均留存。task8关炉有独立 `invariant_regression` 字段和失败原因；00该字段为null且不新增过程罚分。详见[032配套回复](032_round1.md)。

本机没有服务器真实00/013工件；没有把既有52/60、21/60等历史数字当成本次重新核验的结果。真实复用覆盖与差异由下面file-only命令根据实际路径生成。

## 实际测试

最终完整定向命令（纯CPU/fake，无native/GPU）：

```bash
python -m pytest tests/test_nine_source_semantics.py tests/test_headless_nine_runtime.py tests/test_headless_nine_planning.py tests/test_headless_nine_workflow.py tests/test_headless_nine_review_boundaries.py tests/test_headless_nine_cli.py tests/test_headless_nine_integration.py tests/test_headless_offline_scoring.py tests/test_task033_eval_export.py tests/test_headless_normal00_runtime.py tests/test_headless_runner.py tests/test_selected_preparation.py -q --basetemp=.work/pytest033-final
```

实际Windows解释器 `C:/ProgramData/anaconda3/python.exe`，结果 **187 passed in 38.03s，exit0**。新三项×00/10联通使用真实文件producer→验收→归档→计划→原workflow执行→typed evidence/录像→inspect，物理/模型均由CPU fake替代；验证00首成功即停，即使该帧未release；10保留原确认长度。固定队列测试执行exact60且旧六零调用，删除已执行fake目录再continue仍无新增执行。

此前受影响源端组合 **523 passed、12 skipped**（41.94s）：11项可选pinned simulator源码未安装，1项Windows符号链接权限；未尝试native补验。随后新增source adapter映射例被最终187组合覆盖。评分与旧031/013组合阶段 **68 passed**；最后invariant小修及其新增例纳入最终187。以上是重叠分组，不能累加成独立测例总数。`git diff --check`通过。

独立只读审查发现并已修复：缺episode目录被重入队、新00被误标旧合规、成功路径覆盖口径漂移、异质模型导致旧证据连坐、历史输出目录隔离、中断立即误报missing、续跑丢失具体worker错误。独立边界测试修复后3 passed，已纳入最终组合；最新审查没有剩余runtime/source语义阻断。

## 完整命令与交接

[完整runbook](../../docs/task033_nine_task_runbook.md)提供环境变量、pinned权重链接、每一条完整命令及续跑规则。真实CLI入口：

```bash
python -m benchmark.remaining_goals.headless.nine_cli --help
python -m benchmark.remaining_goals.headless.selected_preparation --help
```

顺序为 `runtime-config` → `reuse-index` → 两个 `budget-plan` / `sources-template` → `selected_preparation --mode inspect` → 只读reuse-only汇总。随后由用户分别启动两条 `prepare-missing`，再 `configure`、`dry-plan`，确认各30 ready后启动两个 `run`，最后 `inspect` / `summarize`。所有flags在实现中存在并由CLI测试覆盖；`configure`自动绑定路径，`reuse-index`和来源准备自动生成hash，不让用户手填。

示例配置：[`nine-normal00.example.json`](../../configs/remaining_goals/headless/nine-normal00.example.json)、[`nine-mask10.example.json`](../../configs/remaining_goals/headless/nine-mask10.example.json)。Codex部署时替换runbook中PY/MODEL_PY、OFT与旧run路径为实际服务器绝对路径；不改变已冻结a23目录，也不因共享harness改变重跑旧六。

未来Eval同步工具：

```bash
python scripts/export_task033_eval.py --source-revision ACCEPTED_FULL_COMMIT_SHA --output /path/to/new/LIBERO-Remain-Eval-task033.zip
```

只读同commit Git对象，README与新九任务配置均由该源版本导出；包含完整必要benchmark兼容依赖、运行说明和逐文件SHA，排除旧90配置、原始数据、权重与研究讨论。源commit不存在许可证则如实记not_present，不代替项目授权。临时Git树测试证明dirty/untracked不入包、输出不覆盖、所选commit固定。另对实现SHA生成本地未验收preview，核对98个payload文件digest，并从解包目录执行纯文件budget-plan得到expected90/new30。**没有把本轮源码擅称accepted，也没有发布或更新Eval库。** 方法库仅应同步范围/源PR链接，不复制实现。

未完成的真实工作仅为Codex审查/隔离部署后的用户来源制备与新增60条模型评测，以及验收后同版本Eval导出发布。未启动真实实验、训练、额外probe，未重跑旧六，未自动merge或清理历史数据。
